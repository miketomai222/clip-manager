"""SQLite storage layer for clip history."""

import hashlib
import os
import sqlite3
import time
from pathlib import Path

from clip_common.types import ClipEntry, ContentType


def _get_db_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    db_dir = Path(data_home) / "clip-manager"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "clips.db"


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class ClipDatabase:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = _get_db_path()
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text',
                hash TEXT NOT NULL,
                timestamp REAL NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_clips_timestamp ON clips(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_clips_hash ON clips(hash);
        """)
        # Create FTS5 table if it doesn't exist
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS clips_fts
                USING fts5(content, content='clips', content_rowid='id');
            """)
        except sqlite3.OperationalError:
            pass  # FTS5 not available, search will fall back to LIKE

        # Triggers to keep FTS in sync
        self.conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS clips_ai AFTER INSERT ON clips BEGIN
                INSERT INTO clips_fts(rowid, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS clips_ad AFTER DELETE ON clips BEGIN
                INSERT INTO clips_fts(clips_fts, rowid, content) VALUES('delete', old.id, old.content);
            END;
        """)
        self.conn.commit()

    def insert_clip(self, content: str, content_type: ContentType = ContentType.TEXT) -> ClipEntry | None:
        """Insert a clip. Returns None if it's a duplicate of the most recent entry."""
        content_hash = _hash_content(content)

        # Dedup: skip if hash matches most recent entry
        row = self.conn.execute(
            "SELECT hash FROM clips ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row and row["hash"] == content_hash:
            return None

        now = time.time()
        cursor = self.conn.execute(
            "INSERT INTO clips (content, content_type, hash, timestamp, pinned) VALUES (?, ?, ?, ?, 0)",
            (content, content_type.value, content_hash, now),
        )
        self.conn.commit()

        return ClipEntry(
            id=cursor.lastrowid,
            content=content,
            content_type=content_type,
            hash=content_hash,
            timestamp=now,
            pinned=False,
        )

    def get_recent(self, limit: int = 50) -> list[ClipEntry]:
        """Get the most recent clips."""
        rows = self.conn.execute(
            "SELECT * FROM clips ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, query: str) -> list[ClipEntry]:
        """Search clips using FTS5, falling back to LIKE."""
        try:
            rows = self.conn.execute(
                """SELECT clips.* FROM clips_fts
                   JOIN clips ON clips.id = clips_fts.rowid
                   WHERE clips_fts MATCH ?
                   ORDER BY clips.timestamp DESC""",
                (query,),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS not available, fall back to LIKE
            rows = self.conn.execute(
                "SELECT * FROM clips WHERE content LIKE ? ORDER BY timestamp DESC",
                (f"%{query}%",),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def delete_old(self, max_entries: int = 500):
        """Prune history to max_entries, keeping pinned clips."""
        self.conn.execute(
            """DELETE FROM clips WHERE id IN (
                SELECT id FROM clips WHERE pinned = 0
                ORDER BY timestamp DESC
                LIMIT -1 OFFSET ?
            )""",
            (max_entries,),
        )
        self.conn.commit()

    def pin(self, clip_id: int):
        self.conn.execute("UPDATE clips SET pinned = 1 WHERE id = ?", (clip_id,))
        self.conn.commit()

    def unpin(self, clip_id: int):
        self.conn.execute("UPDATE clips SET pinned = 0 WHERE id = ?", (clip_id,))
        self.conn.commit()

    def get_by_id(self, clip_id: int) -> ClipEntry | None:
        row = self.conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]

    def close(self):
        self.conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> ClipEntry:
        return ClipEntry(
            id=row["id"],
            content=row["content"],
            content_type=ContentType(row["content_type"]),
            hash=row["hash"],
            timestamp=row["timestamp"],
            pinned=bool(row["pinned"]),
        )
