"""Shared types for clip-manager."""

from dataclasses import dataclass, field
from enum import Enum
import time


class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    HTML = "html"


@dataclass
class ClipEntry:
    id: int = 0
    content: str = ""
    content_type: ContentType = ContentType.TEXT
    hash: str = ""
    timestamp: float = field(default_factory=time.time)
    pinned: bool = False


# D-Bus constants
DBUS_BUS_NAME = "org.clipmanager"
DBUS_OBJECT_PATH = "/org/clipmanager/Daemon"
DBUS_INTERFACE = "org.clipmanager.Daemon"
