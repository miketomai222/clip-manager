# Enter-to-Paste with Prior Text-Focus Detection

## Current State

Every clip selection — whether by mouse click or Enter key — always calls `_simulate_paste()`
(wtype Ctrl+V) after placing the clip on the clipboard. There is no check for whether a text
input was focused before the clip manager opened. If the user opens the popup while a file
manager, browser toolbar button, or any non-text surface has focus, pressing Enter fires a
spurious Ctrl+V into whatever is focused after the window closes.

## Goal

When the user presses Enter (or activates a row by any means), simulate Ctrl+V paste **only
if** a text-type widget was focused immediately before the clip manager was launched. If no
text widget was active, just copy to clipboard and close — no paste simulation.

## Detection Mechanism

Use **AT-SPI2** (`pyatspi`) to query the currently focused accessible object before the GTK
window presents itself (and steals focus). The check runs in `ClipManagerApp.do_activate()`
before `win.present()` is called.

Roles that qualify as "text input":

| `pyatspi` constant | Examples |
|---|---|
| `ROLE_ENTRY` | address bars, search boxes, single-line inputs |
| `ROLE_TEXT` | multi-line editors (gedit, Mousepad) |
| `ROLE_PASSWORD_TEXT` | password fields |
| `ROLE_TERMINAL` | gnome-terminal, foot, kitty |
| `ROLE_DOCUMENT_FRAME` | browser page with caret / contenteditable |
| `ROLE_DOCUMENT_TEXT` | some rich-text views (LibreOffice) |

The traversal walks the AT-SPI2 tree depth-first, stopping at the first focused object. Since
most apps keep their tree shallow at the focused path, this is fast in practice (<5ms). A
`try/except` wraps the entire traversal; any failure (AT-SPI2 bus not running, pyatspi not
installed) falls back to `False` — clipboard-only, no paste.

## Decisions

1. **Check timing**: `detect_prior_text_focus()` runs synchronously in `do_activate()`,
   before `win.present()`. By the time GTK presents the window, GNOME will have already
   delivered a focus-leave event to the previous app — but AT-SPI2 state updates slightly
   later, so the focused state of the old widget is still readable at this point. If this
   proves flaky, the daemon can be extended to record AT-SPI2 focus before the hotkey fires
   (see "Not Addressed" below).

2. **New module `clip_ui/focus_detect.py`**: Isolates AT-SPI2 logic so `window.py` stays
   clean and the detection is independently testable.

3. **`auto_paste: bool` parameter on `ClipManagerWindow`**: The flag is set once at
   construction and does not change during the window's lifetime.

4. **Both Enter and click follow the same rule**: `_select_clip` is the single call site
   for both keyboard and mouse activation, so the flag applies uniformly. If the user opened
   the popup while a text area was focused, clicking also pastes; if not, neither does. This
   is consistent behavior — the trigger is "was a text area active before I opened this?" not
   "how did I pick the clip?"

5. **Fallback**: If `pyatspi` is unavailable or the traversal raises, `detect_prior_text_focus()`
   returns `False` (copy-only). This is safer than blindly pasting — the user can always
   trigger paste manually with Ctrl+V afterward.

6. **`pyatspi` as a soft dependency**: Add to `pyproject.toml` extras (`[dev]` only, or
   as optional). On Ubuntu 24.04, `python3-pyatspi` is available as a system package (already
   accessible via the `--system-site-packages` venv). No new pip dependency needed.

## Implementation Spike Findings

Explored during initial implementation attempt (not yet merged):

### pyatspi availability

`python3-pyatspi` (v2.46.1-1) is available as a system package but **not yet installed**.
Even with `--system-site-packages`, it won't appear in the venv until installed. Requires
`sudo apt install python3-pyatspi` before the production code can call it. The graceful
`ImportError` fallback in `detect_prior_text_focus()` means the app still works without it —
clipboard-only mode. Tests mock the entire module via `sys.modules` so they pass regardless
of whether the system package is present.

### focus_detect.py test strategy

`focus_detect.py` is pure Python with no GTK dependency; `pyatspi` can be fully replaced
with `unittest.mock` objects injected via `sys.modules['pyatspi']` before the import.
`_find_focused` takes accessible objects as plain duck-typed args so it can be tested with
`MagicMock` instances directly without any special GTK setup.

### window.py / __main__.py test strategy

`ClipManagerWindow` inherits from `Gtk.ApplicationWindow`. To unit-test `_select_clip`
without a display:
1. Before importing `clip_ui.window`, inject a real Python base class in place of
   `Gtk.ApplicationWindow` via `sys.modules['gi.repository.Gtk'].ApplicationWindow`
2. Create the instance with `object.__new__(ClipManagerWindow)` to skip `__init__`
3. Manually set the instance attrs the method under test depends on (`_auto_paste`,
   `_closed`, `_daemon`)
4. Patch `gi.repository.GLib.timeout_add` to a `MagicMock` and inspect its calls

This avoids a live Wayland/X11 display while still exercising the real method body.

## What Is Not Addressed

- **Daemon-side pre-detection**: A more robust approach would have the daemon register an
  AT-SPI2 focus listener and record the last focused role *before* the hotkey fires, then
  pass `auto_paste` to the UI via a D-Bus method argument on launch. This eliminates any
  timing race. Left for a future spec if the `do_activate()` timing proves unreliable.

- **Per-app overrides**: Some apps (electron apps, some terminals) expose incomplete
  AT-SPI2 trees and a focused text area may not appear. No special-casing planned; the
  fallback (copy-only) is acceptable for these edge cases.

- **Visual indication**: No UI change to signal whether paste-on-select is active. The
  behavior is implicit (same as before the window was opened).

## Implementation Checklist

- [ ] Create `clip_ui/focus_detect.py`:
  - `_TEXT_ROLES` set of qualifying `pyatspi.Role.*` constants
  - `_find_focused(accessible) -> pyatspi.Accessible | None` — recursive DFS, stops at
    first `STATE_FOCUSED` node, max depth 20 to bound worst case
  - `detect_prior_text_focus() -> bool` — calls `pyatspi.Registry.getDesktop(0)`,
    iterates top-level apps, calls `_find_focused`, checks role; catches all exceptions,
    returns `False` on any failure
- [ ] In `clip_ui/window.py`:
  - Add `auto_paste: bool = False` parameter to `ClipManagerWindow.__init__`; store as
    `self._auto_paste`
  - In `_select_clip`: gate the `_simulate_paste()` call (and the `GLib.timeout_add`
    leading to it) on `self._auto_paste`
- [ ] In `clip_ui/__main__.py`:
  - In `ClipManagerApp.do_activate()`, call `detect_prior_text_focus()` before creating
    `ClipManagerWindow`; pass result as `auto_paste=` kwarg
- [ ] Tests (`tests/test_focus_detect.py`) — `detect_prior_text_focus()`:
  - **Text roles → True**: focused object is `ROLE_ENTRY`, `ROLE_TEXT`, `ROLE_PASSWORD_TEXT`,
    `ROLE_TERMINAL`, `ROLE_DOCUMENT_FRAME`, `ROLE_DOCUMENT_TEXT` (one test per role)
  - **Non-text roles → False**: focused object is `ROLE_PUSH_BUTTON`, `ROLE_MENU_ITEM`,
    `ROLE_FRAME` (window title bar)
  - **No focused object → False**: tree has objects but none carry `STATE_FOCUSED`
  - **Empty desktop → False**: `getDesktop(0).childCount == 0`
  - **Focused object is deeply nested → True**: focused text widget is 5 levels deep inside
    an app; verifies DFS traversal reaches it
  - **Focused object is in a non-first app → True**: first app in desktop has no focused
    object; second app has a focused `ROLE_ENTRY`; verifies the per-app loop continues
  - **Depth limit respected → False**: tree is 21 levels deep (beyond max depth 20); verifies
    the traversal stops and does not return a spurious match below the limit
  - **`getDesktop` raises → False**: simulates AT-SPI2 bus not running
  - **`pyatspi` import fails → False**: patch the import to raise `ImportError`; verifies
    the module-level guard catches it and the public function still returns `False`
  - **`getState()` raises on one node → skips that node, continues**: one object throws on
    `getState()`; a sibling with `STATE_FOCUSED` + `ROLE_ENTRY` is still found and returns
    `True`
  - **`getRole()` raises on focused node → False**: object has `STATE_FOCUSED` but `getRole()`
    raises; verifies the exception is swallowed and the function returns `False`
  - **`childCount` raises on a node → skips children, continues**: verifies partial AT-SPI2
    tree failures do not crash the traversal

- [ ] Tests (`tests/test_window_auto_paste.py`) — `ClipManagerWindow._select_clip`:
  - **`auto_paste=True`, plain-text clip**: `_simulate_paste` is scheduled via
    `GLib.timeout_add` after the window closes
  - **`auto_paste=False`, plain-text clip**: `_simulate_paste` is **not** scheduled;
    clipboard is still set via `daemon.SelectEntry`
  - **`auto_paste=True`, HTML clip**: window hides, both paste and destroy timeouts are
    scheduled
  - **`auto_paste=False`, HTML clip**: window hides, destroy timeout is scheduled, paste
    timeout is **not** scheduled
  - **`auto_paste=False` still closes window**: `_closed` is set and `close()` is called
    even when paste is suppressed

- [ ] Tests (`tests/test_main_auto_paste.py`) — `ClipManagerApp.do_activate()`:
  - `detect_prior_text_focus()` returning `True` results in `ClipManagerWindow` constructed
    with `auto_paste=True`
  - `detect_prior_text_focus()` returning `False` results in `ClipManagerWindow` constructed
    with `auto_paste=False`
