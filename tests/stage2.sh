#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Stage 2: Storage Layer ==="

echo "Running DB unit tests..."
python3 -m pytest tests/test_db.py -v

echo "=== Stage 2: PASSED ==="
