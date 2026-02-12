# Stage 6 — Global Hotkey + Paste Mechanism
*Depends on: Stage 4 | Parallel with: Stage 5*

**Goal:** Ctrl+\` opens the popup; selecting a clip pastes into the previous window.

**Work:**
- **Hotkey registration:** Use GNOME custom keybinding via `gsettings` (most reliable on GNOME 46)
  - Script/installer that registers `Ctrl+grave` → `python3 -m clip_ui` via `org.gnome.settings-daemon.plugins.media-keys`
  - Alternative: `xdg-desktop-portal` GlobalShortcuts (more portable but needs consent dialog)
- **Paste mechanism** in `clip_ui`:
  - On clip selection: call `SelectEntry` (daemon sets wl clipboard), close popup, then simulate Ctrl+V via `wtype` subprocess
  - Small delay (~100ms) between close and keystroke to let focus return
- **Window focus tracking** in daemon: remember the active window before popup opens so paste targets the right window

**Key dependencies:** `subprocess` (for `wtype`), `dbus-python` (for portal if needed)

**External deps:** `wtype` (Wayland keystroke simulation)

**Test script** (`tests/stage6.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 6: Global Hotkey + Paste ==="

echo "Checking wtype is installed..."
which wtype || { echo "FAIL: wtype not installed (sudo apt install wtype)"; exit 1; }

echo "Testing clipboard set + paste simulation..."
echo "paste-test-string" | wl-copy
CLIP=$(wl-paste)
if [ "$CLIP" = "paste-test-string" ]; then
    echo "Clipboard set/get works."
else
    echo "FAIL: clipboard round-trip failed"
    exit 1
fi

echo ""
echo ">> MANUAL INTEGRATION TEST:"
echo ">>   1. Open a text editor (e.g., gedit)"
echo ">>   2. Copy a few different strings"
echo ">>   3. Press Ctrl+\` to open the clip manager popup"
echo ">>   4. Select a clip"
echo ">>   5. Verify it was pasted into the editor"
echo ""

echo "=== Stage 6: MANUAL VERIFICATION NEEDED ==="
```

**Deliverable:** Ctrl+\` opens popup from anywhere; selecting a clip pastes it into the previous window.
