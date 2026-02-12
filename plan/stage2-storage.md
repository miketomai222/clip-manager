# Stage 2 — Storage Layer (SQLite)
*Depends on: Stage 1 | Parallel with: Stage 3*

**Goal:** Daemon can persist and query clip entries in SQLite.

**Work:**
- `clipd/db.py`: open/create DB at `~/.local/share/clip-manager/clips.db`
- Schema: `clips` table (id INTEGER PK, content TEXT, content_type TEXT, hash TEXT, timestamp INTEGER, pinned BOOLEAN)
- FTS5 virtual table for full-text search on `content`
- Functions: `insert_clip()`, `get_recent(limit)`, `search(query)`, `delete_old(max_entries)`, `pin/unpin(id)`
- Deduplication: on insert, if hash matches most recent entry, skip
- Use `XDG_DATA_HOME` (or `~/.local/share`) for DB path

**Key dependencies:** `sqlite3` (stdlib), `hashlib` (stdlib)

**Test script** (`tests/stage2.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 2: Storage Layer ==="

echo "Running DB unit tests..."
python3 -m pytest tests/test_db.py -v

echo "=== Stage 2: PASSED ==="
```

**Unit tests in `tests/test_db.py`:**
- Insert a clip, retrieve it by recency
- Insert duplicate, verify no new row
- Insert 501 clips, verify pruning to 500
- FTS search returns matching clips
- Pin a clip, prune, verify pinned clip survives

**Deliverable:** All DB unit tests pass. Can round-trip clip entries through SQLite.
