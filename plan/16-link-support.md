# HTML Clipboard Preservation (Links in Rich Text)

## Current State

When a clipboard change is detected, `clipboard.py` runs `wl-paste --no-newline` with no
`--type` flag, which returns the `text/plain` representation of the clipboard. This is then
stored as `ContentType.TEXT`.

When the user copies rich text from a browser (e.g. a paragraph with embedded hyperlinks),
the clipboard contains both `text/html` (with `<a href="...">` intact) and `text/plain`
(bare text, links stripped). Clip Manager discards the HTML and stores only the plain text.

`ContentType.HTML` already exists in `clip_common/types.py` but is never written or read
anywhere in the codebase.

## Problem

When the user copies rich text containing hyperlinks and later pastes from Clip Manager, the
links are gone — only the bare anchor text survives. The root cause is that the HTML clipboard
target is never captured.

## Decisions

1. **Capture HTML when available.** On each clipboard change event, call
   `wl-paste --list-types` to inspect available MIME types. If `text/html` is present, capture
   it with `wl-paste --type text/html` and store as `ContentType.HTML`. Otherwise fall back to
   the existing `wl-paste --no-newline` path (`ContentType.TEXT`). Do not store both — the HTML
   entry is the canonical representation; plain text is derivable from it.

2. **Plain text for display and search.** `ContentType.HTML` clips store raw HTML in the
   `content` column. For the UI preview in `ClipRow` and for FTS indexing, strip HTML tags to
   produce a plain text version. Use a simple regex or `html.parser` — no heavy dependency
   needed. Do this at read time (not stored as a separate column).

3. **Paste HTML clips offering both `text/html` and `text/plain`.** When the user selects an
   HTML clip, `clip_ui` sets the clipboard directly via the GTK4 `Gdk.Clipboard` API using
   `Gdk.ContentProvider.new_union()` with two providers: one for `text/html` (the raw stored
   HTML) and one for `text/plain` (the stripped plain text). It then calls `wtype` to simulate
   paste, as it does today.

   `clip_ui` is in the foreground when the user makes a selection, so `Gdk.Clipboard` works
   correctly (the background-app limitation only affects `clipd`). `clipd`'s `SelectEntry`
   D-Bus method continues to handle plain-text clips unchanged via `wl-copy`.

   Rich-text destinations (browsers, Google Docs, email composers) receive the HTML with
   links intact. Plain-text destinations (terminals, text editors) receive the stripped
   plain text. Both use cases work without any action from the user.

4. **Deduplication.** The existing hash-based deduplication compares `content` directly. HTML
   clips hash the raw HTML — two copies of the same page with the same markup will deduplicate
   correctly. No change needed.

5. **FTS trigger.** Extend the `clips_ai`/`clips_ad` trigger guard from
   `content_type = 'text'` to `content_type IN ('text', 'html')`. Index the raw HTML — FTS5
   trigram will still match plaintext search terms that appear in the HTML source. (Tag names
   like `href`, `span`, etc. may appear as noise hits; acceptable given the trigram index
   already has this characteristic for code snippets.)

6. **No UI type badge.** HTML clips show the same row layout as text clips, with the
   stripped plain text as the preview. A visual indicator adds complexity and little value
   for the user — they copied some text and want it back as they copied it.

## What Is Not Addressed

- **Retroactive conversion** — existing `TEXT` clips that happen to contain HTML markup are
  not reclassified.

- **Images embedded in HTML** — if the clipboard contains `image/png` alongside `text/html`,
  the image data is ignored; only the HTML markup is stored.

## Implementation Checklist

- [ ] In `clipboard.py`: add `_get_clipboard_html() -> str | None` that calls
  `wl-paste --type text/html` 
- [ ] In `_read_and_notify()`: check `wl-paste --list-types` for `text/html`; if present call
  `_get_clipboard_html()` and pass `ContentType.HTML`, otherwise use existing text path
- [ ] Add `_strip_html(html: str) -> str` helper (stdlib `html.parser`) in `clip_common`
- [ ] In `clip_ui/window.py` paste handler: when the selected entry is `ContentType.HTML`,
  set the clipboard via `Gdk.Display.get_default().get_clipboard().set_content(
  Gdk.ContentProvider.new_union([html_provider, text_provider]))` then call `wtype` as
  normal; skip the `SelectEntry` D-Bus call for HTML clips
- [ ] In `ClipRow.__init__`: call `_strip_html()` on content before building the preview when
  `content_type == 'html'`
- [ ] Update `clips_ai`/`clips_ad` FTS trigger guard to include `'html'`
- [ ] Write tests: HTML clip captured when `text/html` in types, plain-text clip when not,
  `_strip_html` covers common tag patterns, `SelectEntry` uses correct `wl-copy` args for each
  content type; `clip_ui` paste sets both `text/html` and `text/plain` for HTML entries
