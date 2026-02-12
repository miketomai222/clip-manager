"""Clipboard monitoring via wl-paste --watch."""

import logging
import subprocess
import threading
from typing import Callable

from clip_common.types import ContentType

logger = logging.getLogger(__name__)


class ClipboardMonitor:
    """Monitors the Wayland clipboard using wl-paste --watch."""

    def __init__(self, on_new_clip: Callable[[str, ContentType], None]):
        self._on_new_clip = on_new_clip
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        """Start monitoring clipboard changes in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._process:
            self._process.terminate()
            self._process = None

    def _watch_loop(self):
        """Run wl-paste --watch to detect clipboard changes."""
        while self._running:
            try:
                # wl-paste --watch runs a command each time clipboard changes
                # We use it to invoke cat, which prints the new content to stdout
                self._process = subprocess.Popen(
                    ["wl-paste", "--watch", "cat"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self._read_output()
            except FileNotFoundError:
                logger.error("wl-paste not found. Install wl-clipboard.")
                break
            except Exception:
                logger.exception("Clipboard monitor error")
                if self._running:
                    import time
                    time.sleep(1)

    def _read_output(self):
        """Read lines from wl-paste --watch output."""
        assert self._process and self._process.stdout
        buffer = []
        while self._running:
            data = self._process.stdout.read(4096)
            if not data:
                break
            # wl-paste --watch cat outputs the full clipboard content
            # followed by the next content when clipboard changes.
            # We accumulate and deliver on each clipboard change.
            text = data.decode("utf-8", errors="replace")
            buffer.append(text)

        # Process any remaining buffered content
        if buffer:
            content = "".join(buffer).strip()
            if content:
                self._on_new_clip(content, ContentType.TEXT)


class WlPasteWatcher:
    """Alternative clipboard watcher using wl-paste --watch with a script approach.

    Runs `wl-paste --watch sh -c 'cat; echo "\\0CLIP_SEP\\0"'` to get
    clipboard content with separators between changes.
    """

    def __init__(self, on_new_clip: Callable[[str, ContentType], None]):
        self._on_new_clip = on_new_clip
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_content: str | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._process:
            self._process.terminate()
            self._process = None

    def _watch_loop(self):
        SEPARATOR = "\x00CLIP_SEP\x00"
        while self._running:
            try:
                self._process = subprocess.Popen(
                    ["wl-paste", "--watch", "sh", "-c",
                     'cat; printf "\\0CLIP_SEP\\0\\n"'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                assert self._process.stdout
                buf = ""
                while self._running:
                    data = self._process.stdout.read(4096)
                    if not data:
                        break
                    buf += data.decode("utf-8", errors="replace")
                    while SEPARATOR in buf:
                        clip_content, buf = buf.split(SEPARATOR, 1)
                        clip_content = clip_content.strip()
                        if clip_content and clip_content != self._last_content:
                            self._last_content = clip_content
                            self._on_new_clip(clip_content, ContentType.TEXT)
            except FileNotFoundError:
                logger.error("wl-paste not found. Install wl-clipboard.")
                break
            except Exception:
                logger.exception("Clipboard monitor error")
                if self._running:
                    import time
                    time.sleep(1)


def get_current_clipboard() -> str | None:
    """Get the current clipboard content using wl-paste."""
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None
