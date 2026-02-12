#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

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
