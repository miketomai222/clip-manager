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


def _check_sender(sender: str | None) -> None:
    """Raise DBusException if sender is not the current user.

    Session bus access is already limited to the user's session, but this
    adds defense-in-depth against compromised processes running as the same
    user that attempt to read clipboard history or manipulate clips.
    """
    if sender is None:
        return  # local call (e.g., unit tests) — allow
    try:
        bus = dbus.SessionBus()
        sender_uid = bus.get_unix_user(sender)
        if sender_uid != os.getuid():
            raise dbus.DBusException(
                "Access denied: sender UID mismatch",
                name="org.clipmanager.AccessDenied",
            )
    except dbus.DBusException:
        raise
    except Exception:
        logger.warning("Sender UID check failed, allowing call")


class ClipDaemonService(dbus.service.Object):
    def __init__(self, db: ClipDatabase):
        self.db = db
        self._ui_proc: subprocess.Popen | None = None
        self._watcher = None
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(DBUS_BUS_NAME, bus)
        super().__init__(bus_name, DBUS_OBJECT_PATH)
        logger.info("D-Bus service registered: %s", DBUS_BUS_NAME)

    def set_watcher(self, watcher) -> None:
        self._watcher = watcher

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="s",
                         sender_keyword="sender")
    def GetRecent(self, limit, sender=None):
        """Return recent clips as JSON array."""
        _check_sender(sender)
        limit = max(1, min(int(limit), 1000))
        entries = self.db.get_recent(limit)
        return json.dumps([_entry_to_dict(e) for e in entries])

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="s", out_signature="s",
                         sender_keyword="sender")
    def Search(self, query, sender=None):
        """Search clips, return as JSON array."""
        _check_sender(sender)
        entries = self.db.search(str(query))
        return json.dumps([_entry_to_dict(e) for e in entries])

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="b",
                         sender_keyword="sender")
    def SelectEntry(self, clip_id, sender=None):
        """Set clipboard to the content of the given clip entry."""
        _check_sender(sender)
        if self._watcher:
            self._watcher.try_reconnect()
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
                         in_signature="u", out_signature="b",
                         sender_keyword="sender")
    def PinEntry(self, clip_id, sender=None):
        """Pin a clip entry."""
        _check_sender(sender)
        entry = self.db.get_by_id(int(clip_id))
        if not entry:
            return False
        return self.db.pin(int(clip_id))

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="u", out_signature="b",
                         sender_keyword="sender")
    def UnpinEntry(self, clip_id, sender=None):
        """Unpin a clip entry."""
        _check_sender(sender)
        entry = self.db.get_by_id(int(clip_id))
        if not entry:
            return False
        self.db.unpin(int(clip_id))
        return True

    @dbus.service.method(DBUS_INTERFACE,
                         in_signature="", out_signature="b",
                         sender_keyword="sender")
    def ToggleUI(self, sender=None):
        """Toggle the UI popup open/closed."""
        _check_sender(sender)
        if self._ui_is_running():
            logger.info("ToggleUI: closing UI (pid %d)", self._ui_proc.pid)
            self._ui_proc.terminate()
            self._ui_proc = None
            return False  # UI is now closed
        else:
            if self._watcher:
                self._watcher.try_reconnect()
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
