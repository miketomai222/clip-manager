#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 9: Toggle Hotkey ==="

echo "Starting daemon..."
python3 -m clipd > /tmp/clipd-test.log 2>&1 &
DPID=$!
sleep 2

echo "Populating a test clip..."
echo "toggle test" | wl-copy
sleep 0.5

echo "Toggle ON (should open UI)..."
gdbus call --session --dest org.clipmanager \
  --object-path /org/clipmanager/Daemon \
  --method org.clipmanager.Daemon.ToggleUI
sleep 1

echo "Toggle OFF (should close UI)..."
gdbus call --session --dest org.clipmanager \
  --object-path /org/clipmanager/Daemon \
  --method org.clipmanager.Daemon.ToggleUI
sleep 1

echo ""
echo ">> MANUAL VERIFICATION:"
echo ">>   1. Press Ctrl+\` — popup opens"
echo ">>   2. Press Ctrl+\` again — popup closes"
echo ">>   3. Press Ctrl+\` again — popup opens again"
echo ""

kill $DPID 2>/dev/null || true
wait $DPID 2>/dev/null || true

rm -f /tmp/clipd-test.log
echo "=== Stage 9: MANUAL VERIFICATION NEEDED ==="
