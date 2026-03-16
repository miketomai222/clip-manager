# Stage 5 — GTK4 Popup UI
*Depends on: Stage 4 | Parallel with: Stage 6*

**Goal:** A GTK4 window that shows clipboard history fetched over D-Bus.

**Work:**
- `clip_ui/__main__.py`: GTK4 application setup (`Gtk.Application`)
- `clip_ui/window.py`: popup window (`Gtk.ApplicationWindow`)
  - Search bar at top (`Gtk.SearchEntry`)
  - Scrollable vertical list of clips (`Gtk.ListBox` or `Gtk.ListView`)
  - Each row: truncated text preview + timestamp
  - Type-to-filter (calls `Search` over D-Bus)
  - Enter/click on a row: calls `SelectEntry` over D-Bus, then closes window
  - Escape: closes window
- Window positioning: center on screen, no titlebar decorations (popup feel)
- Keyboard navigation: arrow keys move selection, Enter selects

**Key dependencies:** `PyGObject` (`gi.repository.Gtk`), `dbus-python` or `pydbus` (client side)

**Test script** (`tests/stage5.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 5: GTK4 Popup UI ==="

echo "Starting daemon..."
python3 -m clipd > /tmp/clipd-test.log 2>&1 &
DPID=$!
sleep 2

echo "Populating test clips..."
echo "clip one" | wl-copy && sleep 0.5
echo "clip two" | wl-copy && sleep 0.5
echo "clip three" | wl-copy && sleep 0.5

echo "Launching UI..."
python3 -m clip_ui &
UPID=$!

echo ""
echo ">> MANUAL VISUAL TEST:"
echo ">>   1. Popup should show 3 clips (clip three, clip two, clip one)"
echo ">>   2. Type in search bar to filter"
echo ">>   3. Arrow keys to navigate, Enter to select"
echo ">>   4. Press Escape to close"
echo ""

wait $UPID 2>/dev/null || true
kill $DPID 2>/dev/null || true
wait $DPID 2>/dev/null || true

rm -f /tmp/clipd-test.log
echo "=== Stage 5: MANUAL VERIFICATION NEEDED ==="
```

**Deliverable:** Popup opens, shows clip history, search filters results, selecting a clip sets the clipboard.
