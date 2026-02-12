#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 3: Clipboard Monitoring ==="

echo "Checking wl-copy is available..."
which wl-copy || { echo "FAIL: wl-copy not found (sudo apt install wl-clipboard)"; exit 1; }

echo "Starting clipboard monitor in test mode..."
python3 -m clipd --test-clipboard > /tmp/clip-test-output.txt 2>&1 &
PID=$!
sleep 2

echo "Copying test string to clipboard..."
echo "hello from stage3 test" | wl-copy
sleep 1

kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true

echo "Checking output..."
if grep -q "hello from stage3 test" /tmp/clip-test-output.txt; then
    echo "Clipboard change detected successfully."
else
    echo "FAIL: clipboard change not detected"
    cat /tmp/clip-test-output.txt
    exit 1
fi

rm -f /tmp/clip-test-output.txt
echo "=== Stage 3: PASSED ==="
