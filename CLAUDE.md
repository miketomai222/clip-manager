# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clip Manager is a clipboard history manager for Ubuntu 24.04 (GNOME 46, Wayland), inspired by Ditto. Python 3.11+ with GTK4 UI, D-Bus IPC, and SQLite storage. All stages (1-8) are implemented.

## Environment Setup

Always use a venv for Python development. Create it with system site packages so PyGObject and dbus-python (which require system-level C libraries) are available:

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -e ".[dev]"
```

## Commands

All commands assume the venv is activated (`source .venv/bin/activate`).

```bash
# Run daemon
python3 -m clipd

# Run daemon in clipboard test mode (prints clipboard changes to stdout)
python3 -m clipd --test-clipboard

# Run UI
python3 -m clip_ui

# Run all tests
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/test_db.py -v

# Run a single test class or method
python3 -m pytest tests/test_db.py::TestSearch -v
python3 -m pytest tests/test_db.py::TestSearch::test_fts_search -v

# Run stage verification scripts (stages 3-8 require Wayland session)
bash tests/stage2.sh
bash tests/stage3.sh

# Install as systemd service with global hotkey
bash install.sh
```

## Architecture

Three Python packages communicating over D-Bus:

```
clip_common/        Shared types, config, D-Bus constants
    ↑                   ↑
clipd/              clip_ui/
  daemon              GTK4 popup
  - clipboard.py        - window.py
  - db.py (SQLite)
  - dbus_service.py
```

- **clipd** runs as a systemd user service, monitors the Wayland clipboard via `wl-paste --watch`, stores entries in SQLite with FTS5, and exposes them over D-Bus (`org.clipmanager.Daemon`)
- **clip_ui** is a GTK4 popup launched on Ctrl+\`, queries the daemon over D-Bus, and pastes selected clips via `wtype`
- **clip_common** holds `ClipEntry`, `ContentType`, D-Bus interface constants, and `Config` loading from TOML

## Key Paths

- DB file: `~/.local/share/clip-manager/clips.db`
- Config: `~/.config/clip-manager/config.toml` (optional, env override: `CLIP_MANAGER_CONFIG`)
- systemd service: `~/.config/systemd/user/clipd.service`
- Design doc: `plan/design.md`
- Implementation plan: `plan/implementation.md` (tracks stage progress)
- Stage specs: `plan/stage[1-8]-*.md`

## Configuration

Optional TOML config file at `~/.config/clip-manager/config.toml`:

```toml
max_history = 500        # max clips to keep (pinned clips exempt)
hotkey = "ctrl+grave"    # global hotkey
db_path = "~/.local/share/clip-manager/clips.db"
max_image_size = 10485760  # 10MB
```

## D-Bus API

Service: `org.clipmanager.Daemon` on session bus.

Methods:
- `GetRecent(u limit) -> s` — JSON array of recent clips
- `Search(s query) -> s` — JSON array of matching clips (FTS5)
- `SelectEntry(u id) -> b` — set clipboard to clip content
- `PinEntry(u id) -> b` / `UnpinEntry(u id) -> b`

Signals:
- `NewClip(s clip_json)` — emitted when a new clip is captured

## Dependencies

- **PyGObject** for GTK4 bindings (`gi.repository.Gtk`, `gi.repository.GLib`)
- **dbus-python** for D-Bus IPC
- **sqlite3** (stdlib) with FTS5 for full-text search
- **wl-clipboard** (`wl-copy`/`wl-paste`) for Wayland clipboard access
- **wtype** for simulating Ctrl+V paste on Wayland
- **tomllib** (stdlib 3.11+) for config file parsing
