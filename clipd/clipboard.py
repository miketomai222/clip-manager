"""Clipboard monitoring via X11 XFixes selection change notifications.

Uses the XFixes extension (via XWayland) to get event-driven clipboard
change notifications. Only spawns wl-paste once per actual clipboard
change to read the content, eliminating polling and GNOME Shell flicker.
"""

import logging
import os
import select
import subprocess
from typing import Callable

from gi.repository import GLib

from clip_common.types import ContentType

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 2000  # fallback polling interval

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
    """Set up XFixes clipboard monitoring. Returns (display, fd) or None."""
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

        logger.info("Using XFixes clipboard monitoring (event-driven, no polling)")
        return d
    except ImportError:
        logger.warning("python-xlib not installed, falling back to wl-paste polling")
        return None
    except Exception:
        logger.warning("XFixes init failed, falling back to wl-paste polling",
                        exc_info=True)
        return None


class WlPasteWatcher:
    """Clipboard watcher using XFixes for change detection.

    Uses X11 XFixes extension (via XWayland) for event-driven clipboard
    change notifications. Only reads clipboard content (via wl-paste)
    when a change is actually detected. Falls back to periodic wl-paste
    polling if XFixes is unavailable.
    """

    def __init__(self, on_new_clip: Callable[[str, ContentType], None]):
        self._on_new_clip = on_new_clip
        self._source_id: int | None = None
        self._last_content: str | None = None
        self._xdisplay = _init_xfixes()

    def start(self):
        if self._xdisplay is not None:
            fd = self._xdisplay.fileno()
            self._source_id = GLib.io_add_watch(
                fd, GLib.PRIORITY_DEFAULT,
                GLib.IOCondition.IN, self._on_x11_event)
        else:
            self._source_id = GLib.timeout_add(POLL_INTERVAL_MS, self._poll_fallback)

    def stop(self):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None
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

    def _poll_fallback(self) -> bool:
        """Fallback: poll wl-paste when XFixes is unavailable."""
        try:
            self._read_and_notify()
        except Exception:
            logger.exception("Clipboard poll error")
        return True


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
