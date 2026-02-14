"""Clipboard monitoring via polling wl-paste."""

import logging
import subprocess
from typing import Callable

from gi.repository import GLib

from clip_common.types import ContentType

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 500  # milliseconds


class WlPasteWatcher:
    """Clipboard watcher that polls wl-paste for changes.

    Uses GLib.timeout_add to poll on the main thread, avoiding
    threading issues with D-Bus and GLib main loop integration.
    """

    def __init__(self, on_new_clip: Callable[[str, ContentType], None]):
        self._on_new_clip = on_new_clip
        self._source_id: int | None = None
        self._last_content: str | None = None

    def start(self):
        self._source_id = GLib.timeout_add(POLL_INTERVAL_MS, self._poll)

    def stop(self):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None

    def _poll(self) -> bool:
        """Poll clipboard and return True to keep the timer running."""
        try:
            logger.debug("poll: calling wl-paste")
            content = _get_clipboard_text()
            logger.debug("poll: wl-paste returned (%s bytes)", len(content) if content else 0)
            if content is not None and content != self._last_content:
                self._last_content = content
                self._on_new_clip(content, ContentType.TEXT)
        except Exception:
            logger.exception("Clipboard poll error")
        return True  # keep polling


def _get_clipboard_text() -> str | None:
    """Get the current clipboard text content using wl-paste."""
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True, text=True, timeout=2,
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
