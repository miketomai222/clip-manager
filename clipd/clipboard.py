"""Clipboard monitoring via X11 XFixes selection change notifications.

Uses the XFixes extension (via XWayland) to get event-driven clipboard
change notifications. Only spawns wl-paste once per actual clipboard
change to read the content, eliminating polling and GNOME Shell flicker.
"""

import logging
import os
import subprocess
from typing import Callable

from gi.repository import GLib

from clip_common.types import ContentType

logger = logging.getLogger(__name__)

XFIXES_RETRY_INTERVAL_MS = 5000  # retry XFixes init every 5s
XFIXES_MAX_RETRIES = 24  # stop retrying after ~2 minutes

# Minimal environment for wl-paste to avoid GNOME Shell app tracking.
_WLPASTE_ENV: dict[str, str] | None = None


def _get_wlpaste_env() -> dict[str, str]:
    """Build a minimal environment for wl-paste subprocesses."""
    global _WLPASTE_ENV
    if _WLPASTE_ENV is None:
        _WLPASTE_ENV = {}
        for key in ("WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DISPLAY", "HOME", "PATH"):
            val = os.environ.get(key)
            if val is not None:
                _WLPASTE_ENV[key] = val
    return _WLPASTE_ENV


def _init_xfixes():
    """Set up XFixes clipboard monitoring. Returns Display or None."""
    try:
        from Xlib import display
        from Xlib.ext import xfixes

        d = display.Display()
        if not d.has_extension("XFIXES"):
            logger.warning("XFixes extension not available")
            d.close()
            return None

        xfixes.query_version(d)
        root = d.screen().root
        clipboard_atom = d.intern_atom("CLIPBOARD")

        mask = (xfixes.XFixesSetSelectionOwnerNotifyMask
                | xfixes.XFixesSelectionWindowDestroyNotifyMask
                | xfixes.XFixesSelectionClientCloseNotifyMask)
        xfixes.select_selection_input(d, root, clipboard_atom, mask)
        d.flush()

        logger.info("Using XFixes clipboard monitoring (event-driven)")
        return d
    except ImportError:
        logger.error("python-xlib not installed — clipboard monitoring unavailable")
        return None
    except Exception:
        logger.warning("XFixes init failed (XWayland may not be ready yet)",
                        exc_info=True)
        return None


def _send_desktop_notification(summary: str, body: str) -> None:
    """Send a desktop notification via notify-send (best-effort)."""
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=Clip Manager", summary, body],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # notify-send not installed


class WlPasteWatcher:
    """Clipboard watcher using XFixes for change detection.

    Uses X11 XFixes extension (via XWayland) for event-driven clipboard
    change notifications. Only reads clipboard content (via wl-paste)
    when a change is actually detected. If XFixes is unavailable at
    startup, retries periodically until XWayland is ready.
    """

    def __init__(self, on_new_clip: Callable[[str, ContentType], None]):
        self._on_new_clip = on_new_clip
        self._source_id: int | None = None
        self._retry_source_id: int | None = None
        self._xfixes_retries = 0
        self._last_content: str | None = None
        self._xdisplay = _init_xfixes()

    def start(self):
        if self._xdisplay is not None:
            self._start_xfixes()
        else:
            self._start_retrying()

    def _start_xfixes(self):
        """Begin event-driven XFixes monitoring."""
        fd = self._xdisplay.fileno()
        self._source_id = GLib.io_add_watch(
            fd, GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN, self._on_x11_event)

    def _start_retrying(self):
        """Schedule periodic XFixes init retries."""
        logger.warning("Clipboard monitoring inactive — retrying XFixes "
                        "every %ds", XFIXES_RETRY_INTERVAL_MS // 1000)
        self._retry_source_id = GLib.timeout_add(
            XFIXES_RETRY_INTERVAL_MS, self._retry_xfixes)

    def _retry_xfixes(self) -> bool:
        """Periodically retry XFixes init."""
        self._xfixes_retries += 1
        self._xdisplay = _init_xfixes()
        if self._xdisplay is not None:
            self._retry_source_id = None
            self._start_xfixes()
            return False  # stop retrying
        if self._xfixes_retries >= XFIXES_MAX_RETRIES:
            logger.error("XFixes unavailable after %d retries — clipboard "
                         "monitoring disabled. Check that XWayland is running "
                         "and python-xlib is installed.", XFIXES_MAX_RETRIES)
            _send_desktop_notification(
                "Clip Manager",
                "Clipboard monitoring failed — XWayland not available. "
                "Try: systemctl --user restart clipd")
            self._retry_source_id = None
            return False  # stop retrying
        return True  # keep retrying

    def stop(self):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None
        if self._retry_source_id is not None:
            GLib.source_remove(self._retry_source_id)
            self._retry_source_id = None
        if self._xdisplay is not None:
            self._xdisplay.close()
            self._xdisplay = None

    def _on_x11_event(self, fd, condition) -> bool:
        """Called when the X11 connection has data (clipboard change event)."""
        try:
            while self._xdisplay.pending_events():
                self._xdisplay.next_event()
                # Each event means clipboard changed — read the new content
                self._read_and_notify()
        except Exception:
            logger.exception("XFixes event handling error")
        return True  # keep watching

    def _read_and_notify(self):
        """Read clipboard content via wl-paste and notify if changed."""
        content = _get_clipboard_text()
        if content is not None and content != self._last_content:
            self._last_content = content
            self._on_new_clip(content, ContentType.TEXT)


def _get_clipboard_text() -> str | None:
    """Get the current clipboard text content using wl-paste."""
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=2,
            start_new_session=True,
            env=_get_wlpaste_env(),
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except FileNotFoundError:
        logger.error("wl-paste not found. Install wl-clipboard.")
    except subprocess.TimeoutExpired:
        logger.warning("wl-paste timed out after 2s")
    return None


# Public alias
get_current_clipboard = _get_clipboard_text
