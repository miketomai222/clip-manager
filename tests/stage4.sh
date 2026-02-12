#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 4: D-Bus Interface ==="

echo "Starting daemon..."
python3 -m clipd > /tmp/clipd-test.log 2>&1 &
PID=$!
sleep 3

echo "Copying test data..."
echo "dbus test clip" | wl-copy
sleep 1

echo "Querying via D-Bus..."
RESULT=$(busctl --user call org.clipmanager /org/clipmanager/Daemon org.clipmanager.Daemon GetRecent u 5 2>&1)

kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true

if echo "$RESULT" | grep -q "dbus test clip"; then
    echo "D-Bus query returned expected clip."
else
    echo "FAIL: D-Bus query did not return expected clip"
    echo "Result: $RESULT"
    echo "Daemon log:"
    cat /tmp/clipd-test.log
    exit 1
fi

rm -f /tmp/clipd-test.log
echo "=== Stage 4: PASSED ==="
