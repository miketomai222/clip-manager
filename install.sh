#!/usr/bin/env bash
set -euo pipefail

echo "=== Clip Manager Installer ==="

INSTALL_DIR="$HOME/.local/share/clip-manager"
SERVICE_DIR="$HOME/.config/systemd/user"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check dependencies
echo "Checking dependencies..."
for cmd in wl-copy wl-paste wtype python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found. Please install it first."
        case "$cmd" in
            wl-copy|wl-paste) echo "  sudo apt install wl-clipboard" ;;
            wtype) echo "  sudo apt install wtype" ;;
        esac
        exit 1
    fi
done

# Create install directory (owner-only — contains the DB and clipboard history)
echo "Installing to $INSTALL_DIR..."
mkdir -p -m 0700 "$INSTALL_DIR"
chmod 0700 "$INSTALL_DIR" 2>/dev/null || true  # fix existing installs

# Copy project files
for item in clip_common clipd clip_ui pyproject.toml requirements.txt; do
    cp -r "$SCRIPT_DIR/$item" "$INSTALL_DIR/"
done

# Create venv with system site packages (for PyGObject, dbus-python)
echo "Setting up Python environment..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv" --system-site-packages
fi
"$INSTALL_DIR/venv/bin/pip" install -q "$INSTALL_DIR"

# Install systemd service
echo "Installing systemd service..."
mkdir -p "$SERVICE_DIR"
cp "$SCRIPT_DIR/clipd.service" "$SERVICE_DIR/clipd.service"
systemctl --user daemon-reload
systemctl --user enable clipd

# Register GNOME keybinding for Ctrl+`
echo "Registering global hotkey (Ctrl+\`)..."
EXISTING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "[]")

# Check if our keybinding already exists
KEYBINDING_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clip-manager/"
if echo "$EXISTING" | grep -q "clip-manager"; then
    echo "Keybinding already registered."
else
    # Add our path to the list
    if [ "$EXISTING" = "@as []" ] || [ "$EXISTING" = "[]" ]; then
        NEW_LIST="['$KEYBINDING_PATH']"
    else
        # Remove trailing ] and append
        NEW_LIST="${EXISTING%]*}, '$KEYBINDING_PATH']"
    fi
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST" 2>/dev/null || true
fi

# Set the keybinding properties
SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
DCONF_PATH="$KEYBINDING_PATH"
gsettings set "$SCHEMA:$DCONF_PATH" name "Clip Manager" 2>/dev/null || true
gsettings set "$SCHEMA:$DCONF_PATH" command "gdbus call --session --dest org.clipmanager --object-path /org/clipmanager/Daemon --method org.clipmanager.Daemon.ToggleUI" 2>/dev/null || true
gsettings set "$SCHEMA:$DCONF_PATH" binding "<Ctrl>grave" 2>/dev/null || true

# Start the service
echo "Starting daemon..."
systemctl --user start clipd

echo ""
echo "=== Installation complete! ==="
echo "  Daemon: systemctl --user status clipd"
echo "  Hotkey: Ctrl+\` to open clipboard history"
echo "  Uninstall: systemctl --user disable --now clipd && rm -rf $INSTALL_DIR"
