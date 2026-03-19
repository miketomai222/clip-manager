# Search Algorithm Review & Improvements

## Current State

Search is implemented in `clipd/db.py:search()` using SQLite FTS5 with a LIKE fallback.

```python
SELECT clips.* FROM clips_fts
JOIN clips ON clips.id = clips_fts.rowid
WHERE clips_fts MATCH ?
ORDER BY clips.timestamp DESC
```

**Problems with the current approach:**

1. **No relevance ranking** — results are ordered by `timestamp DESC`, ignoring match quality. A clip where the query appears in the first word ranks the same as one where it appears once in 2000 characters.

2. **FTS5 MATCH is token-based, not substring** — FTS5 tokenizes on whitespace/punctuation, so searching for `foo` won't match `foobar`. Users expect substring matching for short queries.

3. **Raw query passed to MATCH** — if the user types a bare word like `hello world`, FTS5 interprets it as `hello AND world`, which is reasonable, but special characters (`"`, `*`, `(`, `)`) cause an `OperationalError` and silently fall back to LIKE. The user never knows why results changed.

4. **LIKE fallback is O(n) full scan** — no index, scans all rows on every keystroke.

5. **No prefix matching** — typing `htt` won't match `https://...` with FTS5 unless the query uses the `*` operator explicitly.

6. **Images are indexed but unsearchable** — binary content is stored in the FTS table, wasting space and potentially causing encoding issues.

7. **No result limit** — `search()` returns all matches; a large history could return thousands of rows on common words like "the".

## Chosen Approach

**FTS5 trigram tokenizer** (`tokenize="trigram"`) as a drop-in replacement for the default tokenizer. This resolves the core issues (no substring match, special-char crashes, LIKE fallback) in one schema change rather than layering query-sanitization heuristics on top of a broken foundation.

Rejected alternatives:
- **Query sanitization** — would fix crashes but not the substring/prefix gap; still need a separate strategy for short queries.
- **Hybrid short/long query routing** — adds branching complexity; trigram handles all query lengths uniformly.
- **Fuzzy / Levenshtein matching** — not needed for a clipboard manager; users know what they copied.

## Decisions

1. **Keep live-as-you-type** (150ms debounce already in place). Favors fast, predictable matching over fuzzy/aggressive approaches.

2. **Adopt FTS5 trigram tokenizer** (`tokenize="trigram"`). This single change resolves problems 2, 3, 4, and 5 from above:
   - Substring and prefix matching work natively — no query sanitization needed.
   - No special-character `OperationalError` — trigram tokenizer treats input as literal substrings.
   - Eliminates the LIKE fallback for normal operation. Keep LIKE only as a compile-time safety net if FTS5 is unavailable.
   - Trade-off (larger index, slower inserts) is negligible at 500–10,000 clips.

3. **Order by `Rejected alternatives:BM25 `rank` as primary sort key, recency as tiebreaker. Boost pinned clips with a small constant (`rank - 1.0` for pinned rows) — simple, no extra columns.

4. **Cap results at 200** (`LIMIT 200` in `search()`). Not configurable — the UI list never needs more than this.

5. **Exclude image clips from FTS index**. Change the `clips_ai` trigger to only insert rows where `new.content_type = 'text'`. Images are not text-searchable; binary content in the trigram index wastes space. Image clips remain visible in `get_recent()`.

6. **No user-visible fallback indicator**. With trigram, the fallback is a last-resort for systems without FTS5 — not a normal path. No UI change needed.

## Implementation Checklist

- [x] Drop and recreate `clips_fts` with `tokenize="trigram"` — `_migrate_fts()` in `clipd/db.py` detects old tokenizer via `sqlite_master`, drops and recreates, runs `rebuild`.
- [x] Update `clips_ai` trigger: add `WHEN new.content_type = 'text'` guard.
- [x] Update `clips_ad` trigger: add matching `WHEN old.content_type = 'text'` guard.
- [x] Rewrite `search()` query: change ORDER BY, add LIMIT 200.
- [x] Add pinned boost to ORDER BY: `ORDER BY (clips_fts.rank - clips.pinned), clips.timestamp DESC`.
- [x] Write/update tests in `tests/test_db.py`: substring match, special chars, image exclusion, result cap, pinned ranking, migration.
