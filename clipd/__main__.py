"""Entry point for the clip-manager daemon."""

import argparse
import logging
import sys

from clip_common import __version__
from clip_common.types import ContentType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("clipd")


def run_test_clipboard():
    """Run in test mode: print clipboard changes to stdout and exit."""
    from gi.repository import GLib

    from clipd.clipboard import WlPasteWatcher

    def on_clip(content: str, ctype: ContentType):
        print(f"[CLIP] {content}", flush=True)

    watcher = WlPasteWatcher(on_new_clip=on_clip)
    watcher.start()

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()


def run_daemon():
    """Run the full daemon with DB + clipboard monitor + D-Bus."""
    from gi.repository import GLib

    from clip_common.config import load_config
    from clipd.clipboard import WlPasteWatcher
    from clipd.db import ClipDatabase
    from clipd.dbus_service import ClipDaemonService

    config = load_config()
    db = ClipDatabase(db_path=config.db_path)
    service = ClipDaemonService(db)

    def on_new_clip(content: str, content_type: ContentType):
        entry = db.insert_clip(content, content_type)
        if entry:
            logger.info("New clip stored: %s...", entry.content[:50])
            db.delete_old(max_entries=config.max_history)
            service.emit_new_clip(entry)

    watcher = WlPasteWatcher(on_new_clip=on_new_clip)

    logger.info("Starting clip-manager daemon v%s", __version__)
    logger.info("Config: max_history=%d, db=%s", config.max_history, config.db_path)

    # Debug heartbeat: confirms GLib main loop is processing timer events
    _heartbeat_count = [0]

    def _heartbeat():
        _heartbeat_count[0] += 1
        logger.info("heartbeat #%d — GLib main loop is alive", _heartbeat_count[0])
        return True  # keep firing

    GLib.timeout_add_seconds(5, _heartbeat)

    watcher.start()

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        db.close()
        logger.info("Daemon stopped.")


def main():
    parser = argparse.ArgumentParser(description="Clip Manager Daemon")
    parser.add_argument("--version", action="version", version=f"clipd {__version__}")
    parser.add_argument("--test-clipboard", action="store_true",
                        help="Test mode: print clipboard changes to stdout")
    parser.add_argument("--debug", action="store_true",
                        help="Enable DEBUG-level logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test_clipboard:
        run_test_clipboard()
    else:
        run_daemon()


if __name__ == "__main__":
    main()
