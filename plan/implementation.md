# Implementation Plan — Clip Manager

## Project Structure

```
clip-manager/
├── clipd/                   (daemon package)
│   ├── __init__.py
│   ├── __main__.py          (entry point)
│   ├── clipboard.py         (clipboard monitoring)
│   ├── db.py                (SQLite storage)
│   └── dbus_service.py      (D-Bus service)
├── clip_ui/                 (GTK4 popup package)
│   ├── __init__.py
│   ├── __main__.py          (entry point)
│   └── window.py
├── clip_common/             (shared types & D-Bus interface)
│   ├── __init__.py
│   └── types.py
├── tests/
│   └── stage*.sh
├── install.sh
├── clipd.service
├── requirements.txt
├── pyproject.toml
└── plan/
    ├── design.md
    └── implementation.md
```

Daemon (`clipd`) and UI (`clip_ui`) as separate Python packages, with shared types in `clip_common`. Runnable via `python -m clipd` and `python -m clip_ui`.

---

## Dependency Graph

```
Stage 1  (Scaffolding)
   │
   ├──────────────────┐
   ▼                  ▼
Stage 2 (Storage)   Stage 3 (Clipboard Monitor)
   │                  │
   ├──────────────────┘
   ▼
Stage 4 (D-Bus Interface)
   │
   ├──────────────────┐
   ▼                  ▼
Stage 5 (GTK4 UI)  Stage 6 (Hotkey + Paste)
   │                  │
   ├──────────────────┘
   ▼
Stage 7 (System Integration)
   │
   ▼
Stage 8 (Polish)
```

**Parallelizable:**
- Stages 2 and 3 can be built in parallel (both depend only on Stage 1)
- Stages 5 and 6 can be built in parallel (both depend only on Stage 4)

---

## Stages

| Stage | Name | Depends on | Parallel with | Key milestone | Details | Status |
|-------|------|------------|---------------|---------------|---------|--------|
| 1 | Scaffolding | — | — | `python -m clipd` and `python -m clip_ui` run | [stage1-scaffolding.md](stage1-scaffolding.md) | **DONE** |
| 2 | Storage (SQLite) | 1 | 3 | DB unit tests pass | [stage2-storage.md](stage2-storage.md) |
| 3 | Clipboard Monitor | 1 | 2 | Detects clipboard changes | [stage3-clipboard-monitor.md](stage3-clipboard-monitor.md) |
| 4 | D-Bus Interface | 2, 3 | — | `busctl` can query clip history | [stage4-dbus.md](stage4-dbus.md) |
| 5 | GTK4 Popup UI | 4 | 6 | Popup shows and filters clips | [stage5-gtk-ui.md](stage5-gtk-ui.md) |
| 6 | Hotkey + Paste | 4 | 5 | Ctrl+\` opens popup, paste works | [stage6-hotkey-paste.md](stage6-hotkey-paste.md) |
| 7 | System Integration | 5, 6 | — | systemd service runs on login | [stage7-system-integration.md](stage7-system-integration.md) |
| 8 | Polish | 7 | — | Config, images, pruning all working | [stage8-polish.md](stage8-polish.md) |
