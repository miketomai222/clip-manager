"""Entry point for the clip-manager UI."""

import argparse
import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from clip_common import __version__
from clip_ui.window import ClipManagerWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


class ClipManagerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.clipmanager.UI")

    def do_activate(self):
        win = ClipManagerWindow(self)
        win.present()


def main():
    parser = argparse.ArgumentParser(description="Clip Manager UI")
    parser.add_argument("--version", action="version", version=f"clip-ui {__version__}")
    args = parser.parse_args()

    app = ClipManagerApp()
    app.run([])


if __name__ == "__main__":
    main()
