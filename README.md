# Clip Manager

A clipboard history manager for Ubuntu 24.04+ (GNOME/Wayland), inspired by [Ditto](https://github.com/sabrogden/Ditto).

Python 3.11+ with a GTK4 popup UI, D-Bus IPC, and SQLite storage with full-text search.

## Features

- Automatic clipboard monitoring via X11 XFixes (event-driven, no polling)
- Searchable clipboard history with FTS5 full-text search
- Pin important clips to keep them permanently
- Global hotkey (Ctrl+`) to open the popup
- Keyboard-driven: arrow keys to navigate, Enter to select and paste
- Runs as a systemd user service
- Deduplication — consecutive identical copies are stored once
- Configurable history size (default 500 clips)
- Local only

## Installation

### Prerequisites

```bash
sudo apt install wl-clipboard wtype python3-gi python3-dbus gir1.2-gtk-4.0
```

### Install

```bash
git clone https://github.com/miketomai222/clip-manager.git
cd clip-manager
bash install.sh
```

This sets up a Python venv, installs the daemon as a systemd user service, and registers the global hotkey.

### Uninstall

```bash
systemctl --user disable --now clipd
rm -rf ~/.local/share/clip-manager
```

## Usage

Once installed, the daemon runs automatically in the background.

- **Ctrl+`** — Open the clipboard history popup
- **Type** — Search/filter clips
- **Up/Down** — Navigate the list
- **Enter** — Paste the selected clip and close
- **Escape** — Close without pasting

## Architecture

Three Python packages communicating over D-Bus:

```
clip_common/          Shared types, config, D-Bus constants
    ↑                     ↑
clipd/                clip_ui/
  Daemon                GTK4 popup
  - clipboard.py          - window.py
  - db.py (SQLite+FTS5)
  - dbus_service.py
```

- **clipd** — systemd user service that monitors the clipboard and stores entries in SQLite. Uses X11 XFixes via XWayland for event-driven change detection, with `wl-paste` to read content only on actual changes.
- **clip_ui** — GTK4 popup window launched via D-Bus. Queries the daemon for history/search and pastes via `wtype`.
- **clip_common** — Shared `ClipEntry` type, `ContentType` enum, D-Bus constants, and TOML config loading.

## Configuration

Optional config file at `~/.config/clip-manager/config.toml`:

```toml
max_history = 500
db_path = "~/.local/share/clip-manager/clips.db"
```

## Development

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -e ".[dev]"

# Run daemon directly
python3 -m clipd --debug

# Run tests
python3 -m pytest tests/ -v
```

## Dependencies

- [PyGObject](https://pygobject.gnome.org/) — GTK4 bindings
- [dbus-python](https://dbus.freedesktop.org/doc/dbus-python/) — D-Bus IPC
- [python-xlib](https://github.com/python-xlib/python-xlib) — XFixes clipboard monitoring
- [wl-clipboard](https://github.com/bugaevc/wl-clipboard) — Wayland clipboard access
- [wtype](https://github.com/atx/wtype) — Keyboard input simulation on Wayland
- SQLite with FTS5 (stdlib)

## License

MIT
