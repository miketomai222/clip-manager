# Stage 4 — D-Bus Interface
*Depends on: Stages 2 + 3 | Parallel with: —*

**Goal:** Daemon exposes clipboard history over D-Bus. UI client can query it.

**Work:**
- `clip_common/types.py`: D-Bus interface name and object path constants (`org.clipmanager.Daemon`)
- `clipd/dbus_service.py`: implement the D-Bus service
  - Methods: `GetRecent(limit) -> Vec<ClipEntry>`, `Search(query) -> Vec<ClipEntry>`, `SelectEntry(id)` (sets clipboard to entry), `PinEntry(id)`, `UnpinEntry(id)`
  - Signals: `NewClip(ClipEntry)` (emitted when a new clip is captured)
- `clipd/__main__.py`: wire together clipboard monitor → DB → D-Bus service
  - On new clip: insert into DB, emit `NewClip` signal
  - On `GetRecent`/`Search`: query DB, return results
  - Run GLib main loop to serve D-Bus + clipboard monitoring

**Key dependencies:** `dbus-python` or `pydbus`, `gi.repository.GLib` for main loop

**Test script** (`tests/stage4.sh`):
```bash
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
```

**Unit/integration tests:**
- Mock clipboard source, verify D-Bus `GetRecent` returns inserted clips
- Verify `Search` filters correctly
- Verify `NewClip` signal is emitted

**Deliverable:** Running daemon captures clips and responds to D-Bus queries. `busctl` can retrieve history.
