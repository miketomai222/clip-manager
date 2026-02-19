"""D-Bus service for exposing clipboard history."""

import json
import logging
import os
import signal
import subprocess
import sys

import dbus
import dbus.service
import dbus.mainloop.glib

from clip_common.types import DBUS_BUS_NAME, DBUS_INTERFACE, DBUS_OBJECT_PATH, ClipEntry
from clipd.db import ClipDatabase

logger = logging.getLogger(__name__)

# Initialize the GLib main loop for dbus before creating any bus connections
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)


def _entry_to_dict(entry: ClipEntry) -> dict:
    return {
        "id": entry.id,
        "content": entry.content,
        "content_type": entry.content_type.value,
        "hash": entry.hash,
        "timestamp": entry.timestamp,
        "pinned": entry.pinned,
    }


class ClipDaemonService(dbus.service.Object):
    def __init__(self, db: ClipDatabase):
        self.db = db
        self._ui_proc: subprocess.Popen | None = None
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(DBUS_BUS_NAME, bus)
        super().__init__(bus_name, DBUS_OBJECT_PATH)
        logger.info("D-Bus service registered: %s", DBUS_BUS_NAME)

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="s")
    def GetRecent(self, limit):
        """Return recent clips as JSON array."""
        entries = self.db.get_recent(int(limit))
        return json.dumps([_entry_to_dict(e) for e in entries])

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="s", out_signature="s")
    def Search(self, query):
        """Search clips, return as JSON array."""
        entries = self.db.search(str(query))
        return json.dumps([_entry_to_dict(e) for e in entries])

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="b")
    def SelectEntry(self, clip_id):
        """Set clipboard to the content of the given clip entry."""
        entry = self.db.get_by_id(int(clip_id))
        if not entry:
            return False
        try:
            proc = subprocess.run(
                ["wl-copy"],
                input=entry.content,
                text=True,
                timeout=2,
            )
            return proc.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.error("wl-copy failed")
            return False

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="b")
    def PinEntry(self, clip_id):
        """Pin a clip entry."""
        entry = self.db.get_by_id(int(clip_id))
        if not entry:
            return False
        self.db.pin(int(clip_id))
        return True

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="b")
    def UnpinEntry(self, clip_id):
        """Unpin a clip entry."""
        entry = self.db.get_by_id(int(clip_id))
        if not entry:
            return False
        self.db.unpin(int(clip_id))
        return True

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="", out_signature="b")
    def ToggleUI(self):
        """Toggle the UI popup open/closed."""
        if self._ui_is_running():
            logger.info("ToggleUI: closing UI (pid %d)", self._ui_proc.pid)
            self._ui_proc.terminate()
            self._ui_proc = None
            return False  # UI is now closed
        else:
            logger.info("ToggleUI: opening UI")
            self._ui_proc = subprocess.Popen(
                [sys.executable, "-m", "clip_ui"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True  # UI is now open

    def _ui_is_running(self) -> bool:
        """Check if the UI subprocess is still alive."""
        if self._ui_proc is None:
            return False
        return self._ui_proc.poll() is None

    @dbus.service.signal(DBUS_INTERFACE, signature="s")
    def NewClip(self, clip_json):
        """Signal emitted when a new clip is captured."""
        pass

    def emit_new_clip(self, entry: ClipEntry):
        """Emit the NewClip signal for a new entry.

        Only emits ID and timestamp — content is deliberately excluded
        because D-Bus signals are broadcast to all session bus listeners.
        """
        self.NewClip(json.dumps({
            "id": entry.id,
            "content_type": entry.content_type.value,
            "timestamp": entry.timestamp,
        }))
