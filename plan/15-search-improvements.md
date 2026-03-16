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

## Improvement Directions

### 1. Sanitize / wrap the query before passing to MATCH

Escape or quote the user's raw input so FTS5 never throws. Options:
- Wrap in double-quotes for a phrase search: `"user query"` — exact phrase, safe from special chars.
- Tokenize the input and append `*` to the last token for prefix matching: `hello world*`.
- Strip characters FTS5 treats as operators before building the MATCH expression.

Trade-off: phrase-only kills multi-word AND matching; tokenized prefix is more complex but more useful.

### 2. Rank by relevance using FTS5's built-in `rank`

FTS5 exposes a `rank` column (BM25-based). Replace `ORDER BY timestamp DESC` with a composite:

```sql
ORDER BY rank, clips.timestamp DESC
```

Or weight recency vs. relevance with a formula (e.g., boost pinned clips).

### 3. Hybrid substring + FTS5 for short queries

Short queries (≤3 chars) benefit more from substring matching than token matching. Strategy:
- If `len(query) <= 3`: use `LIKE %query%` with an index-friendly approach, or FTS5 prefix (`query*`).
- If `len(query) > 3`: use FTS5 phrase/token search with rank.

### 4. Skip non-text content in FTS index

Only index `content_type = 'text'` rows. Images produce meaningless tokens and bloat the FTS table. This requires a filtered trigger or a `WHERE` clause on inserts.

### 5. Cap result count

Add `LIMIT 200` (or config-driven) to `search()` so the UI never gets flooded.

### 6. Consider trigram indexing as an alternative

SQLite's FTS5 trigram tokenizer (`tokenize="trigram"`) supports substring and case-insensitive search natively, fixes the prefix/substring gap, and still uses an index. Trade-off: larger index size (~3× vs. standard tokenizer), slower inserts.

## Open Questions

- Should search be live-as-you-type (current) or triggered on Enter? Affects how aggressive prefix/fuzzy matching should be.
- Should pinned clips rank higher than recency/relevance?
- Is there a user-visible indicator when FTS fallback is active?
- What is the realistic history size? At 500 clips (default max), O(n) LIKE is probably fast enough; at 5000+ it becomes noticeable.
- Should image clips be searchable by metadata (timestamp, source app) rather than content?
