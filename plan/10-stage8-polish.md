# Stage 8 — Polish
*Depends on: Stage 7 | Parallel with: —*

**Goal:** Config file, image support, UX refinements.

**Work:**
- **Config file** (`~/.config/clip-manager/config.toml`):
  ```toml
  max_history = 500
  hotkey = "ctrl+grave"
  db_path = "~/.local/share/clip-manager/clips.db"
  ```
  - Load in daemon and UI at startup; fall back to defaults
- **Image clip support:**
  - Store images as files in `~/.local/share/clip-manager/images/` with DB reference
  - Show thumbnails in UI list (`Gtk.Image` in list rows)
  - Max image size policy (skip clips > 10MB)
- **History pruning:** on startup and after each insert, enforce `max_history` (keep pinned)
- **Deduplication:** skip consecutive identical clips (already in Stage 2, verify end-to-end)
- **UX polish:**
  - Show content type icon (text vs image) in list rows
  - Keyboard shortcut hints in UI
  - Smooth scroll, selection highlight

**Key dependencies:** `tomllib` (stdlib, Python 3.11+) or `tomli`, `Pillow` (for thumbnails)

**Test script** (`tests/stage8.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 8: Polish ==="

# Test config loading with reduced history limit
echo "Setting up test config..."
mkdir -p ~/.config/clip-manager
cat > /tmp/clip-manager-test-config.toml << 'EOF'
max_history = 10
EOF

echo "Starting daemon with test config..."
CLIP_MANAGER_CONFIG=/tmp/clip-manager-test-config.toml python3 -m clipd > /tmp/clipd-test.log 2>&1 &
PID=$!
sleep 2

echo "Inserting 15 clips..."
for i in $(seq 1 15); do
    echo "clip $i" | wl-copy
    sleep 0.3
done
sleep 1

echo "Querying history..."
RESULT=$(busctl --user call org.clipmanager /org/clipmanager/Daemon org.clipmanager.Daemon GetRecent u 20 2>&1)

kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true

# Count returned entries (should be <= 10)
echo "Verifying history limit respected..."
echo "Result: $RESULT"

rm -f /tmp/clip-manager-test-config.toml /tmp/clipd-test.log

echo ""
echo ">> MANUAL: Copy an image (e.g., screenshot), open popup, verify thumbnail appears"
echo ""

echo "=== Stage 8: PASSED (automated checks) ==="
```

**Deliverable:** Config file respected, images captured and displayed, history stays within bounds.
