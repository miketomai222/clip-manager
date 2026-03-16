# Fix Clipboard Monitoring — Retrospective & Plan

## Problem
The clipboard manager daemon (`clipd`) does not capture clipboard changes. The UI opens but shows no history.

## Investigation Retrospective

### Finding 1: `wl-paste --watch` doesn't work on GNOME/Mutter
- **Root cause:** `wl-paste --watch` requires the wlroots data-control protocol, which GNOME's Mutter compositor does not implement.
- **Evidence:** Running `wl-paste --watch ...` returns immediately with: *"Watch mode requires a compositor that supports the wlroots data-control protocol"* (exit code 1).
- **Impact:** The original `WlPasteWatcher` (which used `wl-paste --watch`) silently retried every second forever, never capturing anything.

### Finding 2: Plain `wl-paste --no-newline` DOES work
- **Evidence:** `wl-paste --no-newline` returns clipboard content correctly in both interactive shell and from Python.
- **Conclusion:** A polling approach (calling `wl-paste --no-newline` periodically) is viable.

### Finding 3: Threading doesn't work under systemd + dbus-python + GLib
- **What we tried:** Replaced `wl-paste --watch` with a polling thread that calls `subprocess.run(["wl-paste", "--no-newline"])` every 500ms.
- **Result:** Works perfectly when daemon is run directly (`python3 -m clipd`), but fails silently under systemd.
- **Evidence:**
  - `pstree` showed the thread existed and was stuck on `pipe_read`
  - No log messages from the thread ever appeared in journalctl (not even `print(..., flush=True)` to stderr)
  - No `wl-paste` child process visible despite thread being stuck on `pipe_read`
  - Direct run produced "Poll thread started", "Clipboard changed", and "New clip stored" within seconds
- **Hypothesis:** The dbus-python GLib main loop integration (`dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)`) interferes with Python threading under systemd. The thread starts but appears to deadlock immediately — possibly on a GIL interaction with the GLib main loop, or on the `subprocess.run` call itself (which creates pipes that may deadlock with the systemd journal socket).

### Finding 4: GLib.timeout_add approach also produces no output under systemd
- **What we tried:** Replaced the thread with `GLib.timeout_add(500, self._poll)` to run polling on the GLib main loop's own thread.
- **Result:** No clip-related log messages appear under systemd, same as the threading approach.
- **Possible explanations:**
  1. `wl-paste --no-newline` hangs when called from the systemd service context (blocking the main loop)
  2. The GLib main loop itself is not running event sources properly under systemd
  3. There's a Wayland socket access issue from the service that causes `wl-paste` to block

### What we did NOT verify
- Whether `wl-paste` actually completes when run from inside the daemon's process context under systemd (we tested from our shell, not from within the service)
- Whether the `subprocess.run` timeout (2s) actually triggers
- Whether `GLib.timeout_add` callbacks execute at all (we could add a simple heartbeat log)

## Plan

### Step 1: Add a heartbeat log to verify GLib main loop is running
Add a `GLib.timeout_add_seconds(5, heartbeat)` in `run_daemon()` that logs "heartbeat" every 5 seconds. This confirms whether the GLib main loop is processing timer events at all under systemd.

### Step 2: Test if `wl-paste` hangs under systemd
If the heartbeat works but clips aren't captured, the issue is `wl-paste` blocking. Add a log line BEFORE and AFTER the `subprocess.run(["wl-paste", ...])` call in `_poll()` to see if the call returns.

If `wl-paste` hangs: use `subprocess.Popen` with a manual timeout instead of `subprocess.run`, or consider an async approach with `GLib.spawn_async`.

### Step 3: If `wl-paste` doesn't work at all from systemd, use `GLib.spawn_async`
Replace `subprocess.run` with GLib's native async process spawning (`GLib.spawn_async_with_pipes`), which integrates properly with the GLib main loop and avoids blocking.

### Step 4: If the GLib main loop itself isn't running
Check if `dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)` (called at import time in `dbus_service.py`) is interfering. Consider initializing it later, or using a different D-Bus main loop integration.

### Step 5: Clean up
- Remove debug logging (heartbeat, before/after markers)
- Ensure `--test-clipboard` mode still works
- Run all tests
- Verify end-to-end: copy text → appears in UI

## Testing the debug instrumentation

### What was added
- **Heartbeat** (`__main__.py`): `GLib.timeout_add_seconds(5, _heartbeat)` logs `"heartbeat #N — GLib main loop is alive"` at INFO level every 5s.
- **Before/after wl-paste logs** (`clipboard.py`): DEBUG-level `"poll: calling wl-paste"` and `"poll: wl-paste returned (N bytes)"` around the `subprocess.run` call.
- **Timeout warning** (`clipboard.py`): `TimeoutExpired` now logs `"wl-paste timed out after 2s"` instead of silently passing.
- **`--debug` flag** (`__main__.py`): Sets root logger to DEBUG so poll-level messages are visible.

### How to run

```bash
# Direct run with debug logging:
python3 -m clipd --debug

# Or restart the systemd service and watch logs:
systemctl --user restart clipd
journalctl --user -u clipd -f

# To also see DEBUG logs under systemd, add --debug to ExecStart:
#   ExecStart=... python3 -m clipd --debug
```

### Interpreting results

| Heartbeats? | Poll logs? | Diagnosis | Next step |
|---|---|---|---|
| Yes | Yes, wl-paste returns | Everything works — issue was already fixed | Step 5 (clean up) |
| Yes | No poll logs at all | `_poll()` never called — `timeout_add` registration issue | Check `watcher.start()` is called before `loop.run()` |
| Yes | "calling wl-paste" but no "returned" | `wl-paste` hangs under systemd | Step 3 (`GLib.spawn_async`) |
| Yes | "timed out after 2s" repeating | `wl-paste` blocks then times out — Wayland socket issue | Check `WAYLAND_DISPLAY` in service env |
| No | No | GLib main loop not running | Step 4 (investigate D-Bus main loop init) |

## Files to modify
- `clipd/clipboard.py` — polling implementation
- `clipd/__main__.py` — heartbeat, callback wiring
- `clipd/db.py` — already fixed `check_same_thread=False` (keep this)
- `~/.config/systemd/user/clipd.service` — already has `PYTHONUNBUFFERED=1` (keep this)
