# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Clip Manager is a clipboard history manager for Ubuntu 24.04 (GNOME 46, Wayland), inspired by Ditto. Python 3.11+ with GTK4 UI, D-Bus IPC, and SQLite storage.

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

# Run UI
python3 -m clip_ui

# Run all tests
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/test_db.py -v

# Run a single test class or method
python3 -m pytest tests/test_db.py::TestSearch -v
python3 -m pytest tests/test_db.py::TestSearch::test_fts_search -v

# Run stage verification scripts
bash tests/stage1.sh
bash tests/stage2.sh
```

## Architecture

Three Python packages communicating over D-Bus:

```
clip_common/        Shared types (ClipEntry dataclass, ContentType enum, D-Bus constants)
    ↑                   ↑
clipd/              clip_ui/
  daemon              GTK4 popup
  - clipboard.py        - window.py
  - db.py (SQLite)
  - dbus_service.py
```

- **clipd** runs as a systemd user service, monitors the Wayland clipboard, stores entries in SQLite, and exposes them over D-Bus (`org.clipmanager.Daemon`)
- **clip_ui** is a GTK4 popup launched on Ctrl+\`, queries the daemon over D-Bus, and pastes selected clips via `wtype`
- **clip_common** holds `ClipEntry`, `ContentType`, and D-Bus interface constants shared by both

## Key Paths

- DB file: `~/.local/share/clip-manager/clips.db`
- Config (future): `~/.config/clip-manager/config.toml`
- Design doc: `plan/design.md`
- Implementation plan: `plan/implementation.md` (tracks stage progress)
- Stage specs: `plan/stage[1-8]-*.md`

## Implementation Stages

Stages 2+3 are parallel; stages 5+6 are parallel; all others are sequential. See `plan/implementation.md` for the dependency graph and current progress.

## Dependencies

- **PyGObject** for GTK4 bindings (`gi.repository.Gtk`, `gi.repository.GLib`)
- **dbus-python** for D-Bus IPC
- **sqlite3** (stdlib) with FTS5 for full-text search
- **wl-clipboard** (`wl-copy`/`wl-paste`) for Wayland clipboard access
- **wtype** for simulating Ctrl+V paste on Wayland
