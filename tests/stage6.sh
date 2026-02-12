#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 6: Global Hotkey + Paste ==="

echo "Checking wtype is installed..."
which wtype || { echo "FAIL: wtype not installed (sudo apt install wtype)"; exit 1; }

echo "Testing clipboard set + paste simulation..."
echo "paste-test-string" | wl-copy
CLIP=$(wl-paste)
if [ "$CLIP" = "paste-test-string" ]; then
    echo "Clipboard set/get works."
else
    echo "FAIL: clipboard round-trip failed"
    exit 1
fi

echo ""
echo ">> MANUAL INTEGRATION TEST:"
echo ">>   1. Open a text editor (e.g., gedit)"
echo ">>   2. Copy a few different strings"
echo ">>   3. Press Ctrl+\` to open the clip manager popup"
echo ">>   4. Select a clip"
echo ">>   5. Verify it was pasted into the editor"
echo ""

echo "=== Stage 6: MANUAL VERIFICATION NEEDED ==="
