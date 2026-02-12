# Stage 1 — Project Scaffolding
*Depends on: — | Parallel with: —*

**Goal:** Python project structure in place, both entry points run, dependencies declared.

**Work:**
- Create `pyproject.toml` with project metadata and dependencies
- Create package directories: `clipd/`, `clip_ui/`, `clip_common/`
- `clip_common/types.py`: shared `ClipEntry` dataclass (id, content, timestamp, content_type)
- `clipd/__main__.py`: minimal entry point that prints version and exits
- `clip_ui/__main__.py`: minimal entry point that prints version and exits
- `requirements.txt` with initial deps: `PyGObject`, `dbus-python`
- Set up a venv or confirm system packages available

**Key dependencies:** `PyGObject` (GTK4 bindings), `dbus-python` or `pydbus`

**Test script** (`tests/stage1.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 1: Project Scaffolding ==="

echo "Checking Python version..."
python3 --version

echo "Checking GTK4 GI bindings..."
python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print('GTK4 OK')"

echo "Running clipd..."
python3 -m clipd --version

echo "Running clip-ui..."
python3 -m clip_ui --version

echo "=== Stage 1: PASSED ==="
```

**Deliverable:** Both `python3 -m clipd` and `python3 -m clip_ui` run and exit cleanly.
