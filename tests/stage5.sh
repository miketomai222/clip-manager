#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 5: GTK4 Popup UI ==="

echo "Starting daemon..."
python3 -m clipd > /tmp/clipd-test.log 2>&1 &
DPID=$!
sleep 2

echo "Populating test clips..."
echo "clip one" | wl-copy && sleep 0.5
echo "clip two" | wl-copy && sleep 0.5
echo "clip three" | wl-copy && sleep 0.5

echo "Launching UI..."
python3 -m clip_ui &
UPID=$!

echo ""
echo ">> MANUAL VISUAL TEST:"
echo ">>   1. Popup should show 3 clips (clip three, clip two, clip one)"
echo ">>   2. Type in search bar to filter"
echo ">>   3. Arrow keys to navigate, Enter to select"
echo ">>   4. Press Escape to close"
echo ""

wait $UPID 2>/dev/null || true
kill $DPID 2>/dev/null || true
wait $DPID 2>/dev/null || true

rm -f /tmp/clipd-test.log
echo "=== Stage 5: MANUAL VERIFICATION NEEDED ==="
