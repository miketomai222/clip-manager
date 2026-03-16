# Fix clip_ui 100% CPU Usage

## Problem

`clip_ui` (PID shown at 99.7% CPU) is pegging an entire core when running. The UI should be idle most of the time — it's a popup that shows clipboard history and waits for user interaction.

## Suspected Causes

### 1. Focus leave/check loop (most likely)

`_on_focus_leave` fires and schedules `_check_focus` after 100ms. If the window is undecorated (`set_decorated(False)`) and the compositor doesn't give it proper focus, this could cycle:
- Focus leave fires → schedules `_check_focus`
- `_check_focus` calls `self.close()` or returns, but focus leave fires again immediately
- If `is_active()` returns True (window not closed), focus leave keeps re-firing

On Wayland with an undecorated window, the focus behavior may differ from X11 — the compositor may repeatedly send focus-enter/leave events.

### 2. GLib.idle_add re-invocation

`GLib.idle_add(self._load_clips)` runs `_load_clips` when idle. If the D-Bus daemon is unreachable and an unexpected exception type (not `DBusException`) is raised, the idle callback might not be properly removed. However, Python's `idle_add` only repeats if the callback returns `True`/truthy — `_load_clips` returns `None`, so this is less likely.

### 3. D-Bus connection spin

If the daemon isn't running, `dbus.SessionBus().get_object(...)` could throw on every call. If something triggers repeated reconnect attempts inside the GLib main loop, this could cause high CPU.

### 4. CSS/rendering loop

The undecorated window with `border-radius: 8px` CSS might trigger repeated redraws on certain compositors/GPU drivers.

## Investigation Plan

1. **Reproduce and profile**: Run `clip_ui` under `py-spy` or `strace` to see where it spins:
   ```bash
   py-spy top --pid <PID>
   # or
   strace -c -p <PID>
   ```

2. **Add logging to focus handler**: Instrument `_on_focus_leave` and `_check_focus` with counters/timestamps to see if they fire excessively.

3. **Test with daemon running vs not running**: Determine if the spin only happens when the daemon is down.

4. **Test with decorated window**: Temporarily set `self.set_decorated(True)` to rule out compositor focus issues.

## Proposed Fix

Based on investigation, likely one of:

- **Focus loop fix**: Add a guard to prevent re-scheduling `_check_focus` if one is already pending. Or replace the focus-leave-close behavior with a different mechanism (e.g., only close on Escape or clicking outside).
- **D-Bus error handling**: Ensure all D-Bus failures are caught broadly (`except Exception`) and the UI degrades gracefully (shows "daemon not running" message instead of retrying).
- **Idle callback guard**: Ensure `_load_clips` returns `False` explicitly rather than relying on implicit `None`.

## Files to Modify

- `clip_ui/window.py` — main fix location
- `clip_ui/__main__.py` — if app lifecycle changes are needed
