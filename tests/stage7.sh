#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 7: System Integration ==="

echo "Running install script..."
bash install.sh

sleep 2

echo "Checking service status..."
systemctl --user is-active clipd || { echo "FAIL: clipd service not running"; exit 1; }

echo "Checking D-Bus registration..."
busctl --user list | grep -q clipmanager || { echo "FAIL: D-Bus name not registered"; exit 1; }

echo ""
echo ">> MANUAL: Verify tray icon is visible in system tray"
echo ">> MANUAL: After reboot, run: systemctl --user status clipd"
echo ""

echo "=== Stage 7: PASSED (automated checks) ==="
