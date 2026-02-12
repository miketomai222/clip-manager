# Stage 9 — Toggle Hotkey (Close on Re-press)
*Depends on: Stages 6 + 8 | Parallel with: —*

**Goal:** Pressing Ctrl+\` while the popup is already open closes it (toggle behavior).

**Problem:** Currently the GNOME keybinding launches `python3 -m clip_ui` each time. A new process spawns instead of toggling the existing window.

---

## Root Cause

The `Gtk.Application` single-instance approach **does not work** from GNOME custom keybindings. GNOME Shell spawns the command as a direct subprocess (via `g_spawn_async`), bypassing D-Bus activation. The second `python3 -m clip_ui` process either:
- Fails to discover the existing instance's D-Bus registration
- Spawns a brand-new window instead of re-activating the first

`Gtk.Application`'s uniqueness mechanism only works reliably when launched via D-Bus activation (e.g., `.desktop` files with `DBusActivatable=true`), not from arbitrary shell commands in keybindings.

---

## Approach — D-Bus `ToggleUI` method on the daemon (Recommended)

Use the already-running daemon's D-Bus service as the toggle controller. The GNOME keybinding calls a D-Bus method instead of spawning a process.

### Why this approach:
- D-Bus method calls from keybindings are **reliable** — they always reach the daemon
- The daemon is already running and owns the D-Bus name `org.clipmanager`
- Single source of truth for UI state — no race conditions
- Works even if the UI process crashes

### Work:

1. **`clipd/dbus_service.py`**: Add a `ToggleUI()` D-Bus method
   - Track the UI subprocess (PID)
   - If UI is running → kill it (toggle off)
   - If UI is not running → spawn `python3 -m clip_ui` (toggle on)

2. **`clip_ui/__main__.py`**: Revert to simple behavior
   - Remove `self.hold()`, window tracking, and toggle logic
   - Just open the window; close on Escape / focus loss / clip selection (no need for it to stay resident)

3. **`install.sh`**: Change the GNOME keybinding command from:
   ```
   python3 -m clip_ui
   ```
   to:
   ```
   gdbus call --session --dest org.clipmanager --object-path /org/clipmanager/Daemon --method org.clipmanager.Daemon.ToggleUI
   ```

### Alternative approaches considered:

| Approach | Pros | Cons |
|----------|------|------|
| **D-Bus ToggleUI on daemon** | Reliable, clean, no race conditions | Couples daemon to UI lifecycle |
| **PID file + SIGUSR1 signal** | Simple, no D-Bus needed | Race conditions, signal handling in GTK is tricky |
| **Gtk.Application + HANDLES_COMMAND_LINE** | Stays in GTK framework | Still relies on D-Bus registration which fails from keybindings |

---

## Test script (`tests/stage9.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 9: Toggle Hotkey ==="

echo "Starting daemon..."
python3 -m clipd > /tmp/clipd-test.log 2>&1 &
DPID=$!
sleep 2

echo "Populating a test clip..."
echo "toggle test" | wl-copy
sleep 0.5

echo "Toggle ON (should open UI)..."
gdbus call --session --dest org.clipmanager \
  --object-path /org/clipmanager/Daemon \
  --method org.clipmanager.Daemon.ToggleUI
sleep 1

echo "Toggle OFF (should close UI)..."
gdbus call --session --dest org.clipmanager \
  --object-path /org/clipmanager/Daemon \
  --method org.clipmanager.Daemon.ToggleUI
sleep 1

echo ""
echo ">> MANUAL VERIFICATION:"
echo ">>   1. Press Ctrl+\` — popup opens"
echo ">>   2. Press Ctrl+\` again — popup closes"
echo ">>   3. Press Ctrl+\` again — popup opens again"
echo ""

kill $DPID 2>/dev/null || true
wait $DPID 2>/dev/null || true

rm -f /tmp/clipd-test.log
echo "=== Stage 9: MANUAL VERIFICATION NEEDED ==="
```

**Deliverable:** Ctrl+\` toggles the popup open/closed via the daemon's D-Bus `ToggleUI` method. No duplicate windows.
