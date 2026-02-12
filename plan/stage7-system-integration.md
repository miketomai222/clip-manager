# Stage 7 — System Integration
*Depends on: Stages 5 + 6 | Parallel with: —*

**Goal:** Daemon runs as a systemd user service, starts on login, has a tray icon.

**Work:**
- `clipd.service` systemd user unit file:
  ```ini
  [Unit]
  Description=Clip Manager Daemon

  [Service]
  ExecStart=/usr/bin/python3 -m clipd
  WorkingDirectory=%h/clip-manager
  Restart=on-failure

  [Install]
  WantedBy=default.target
  ```
- `install.sh` bash script that:
  - Copies project files to install location (e.g., `~/.local/share/clip-manager/`)
  - Installs the systemd service file to `~/.config/systemd/user/`
  - Registers the GNOME keybinding for Ctrl+\`
  - Runs `systemctl --user enable --now clipd`
- Tray icon: `Gtk.StatusIcon` or libappindicator via `gi.repository.AppIndicator3`
  - Menu: "Show History", "Pause Monitoring", "Quit"
- Autostart: the systemd service handles this

**Test script** (`tests/stage7.sh`):
```bash
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
```

**Deliverable:** Daemon auto-starts on login, survives reboots, tray icon visible.
