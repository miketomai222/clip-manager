# Security Audit — Clip Manager

**Date**: 2026-02-16
**Scope**: Full codebase review (`clipd/`, `clip_ui/`, `clip_common/`, `install.sh`, `clipd.service`)

---

## Summary

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | D-Bus service has no access control | HIGH | Open |
| 2 | Database file world-readable (0644) | MEDIUM | Open |
| 3 | Install directory world-readable (0755) | MEDIUM | Open |
| 4 | Clipboard content size unbounded | MEDIUM | Open |
| 5 | `GetRecent` limit parameter unbounded | MEDIUM | Open |
| 6 | Pinned clips exempt from all limits | MEDIUM | Open |
| 7 | Config/DB paths not validated for symlinks | MEDIUM | Open |
| 8 | `db_path` config accepts arbitrary locations | MEDIUM | Open |
| 9 | Systemd service has no sandboxing (9.8/10 UNSAFE) | HIGH | Open |
| 10 | Config file permissions not enforced | MEDIUM | Open |
| 11 | UMask not set — DB/files created world-readable | MEDIUM | Open |
| 12 | `wl-copy` leaks clipboard content in `/proc/pid/cmdline` | HIGH | Open |
| 13 | `NewClip` D-Bus signal broadcasts content to session bus | HIGH | Open |
| 14 | No core dump protection — crash leaks clipboard history | MEDIUM | Open |
| 15 | Sensitive data persists in process memory unscrubbed | MEDIUM | Open |
| 16 | No mechanism to exclude sensitive content (passwords) | MEDIUM | Open |
| 17 | Log injection via clipboard content | LOW | Open |
| 18 | No network access (local-first confirmed) | PASS | — |
| 19 | SQL queries properly parameterized | PASS | — |
| 20 | Subprocess calls safe (no shell injection) | PASS | — |
| 21 | No code evaluation of clipboard content | PASS | — |
| 22 | Dependencies minimal and trustworthy | PASS | — |

---

## Detailed Findings

### 1. D-Bus Service Has No Access Control — HIGH

**Files**: `clipd/dbus_service.py:34-125`

The D-Bus service `org.clipmanager.Daemon` registers on the session bus with no authentication or policy rules. Any process running under the same user session can call all methods: `GetRecent`, `Search`, `SelectEntry`, `PinEntry`, `UnpinEntry`, `ToggleUI`.

A malicious process could silently read the full clipboard history, manipulate pins, change the active clipboard, or spawn the UI.

**Recommendation**: Add sender UID validation via `sender_keyword`:

```python
@dbus.service.method(..., sender_keyword='sender')
def GetRecent(self, limit, sender=None):
    bus = dbus.SessionBus()
    sender_uid = bus.get_unix_user(sender)
    if sender_uid != os.getuid():
        raise dbus.DBusException("Access denied")
    ...
```

**Note**: Session bus access is already limited to the user's session in most setups, so the practical risk is from malicious processes running as the same user. This is standard for session bus services, but defense-in-depth is worth adding.

---

### 2. Database File World-Readable — MEDIUM

**Files**: `clipd/db.py:28` (SQLite connect), `install.sh`

The database at `~/.local/share/clip-manager/clips.db` is created with default permissions (0644). Any local user can read clipboard history, which likely contains passwords, API keys, and private messages.

**Recommendation**: Set permissions to 0600 after creation in `clipd/db.py`:

```python
import os
self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
os.chmod(self.db_path, 0o600)
```

---

### 3. Install Directory World-Readable — MEDIUM

**Files**: `install.sh:25`

`~/.local/share/clip-manager/` is created with default `mkdir -p` permissions (0755), making installed code and the database listable/readable by other users.

**Recommendation**: Use `mkdir -p -m 0700 "$INSTALL_DIR"` in `install.sh`.

---

### 4. Clipboard Content Size Unbounded — MEDIUM

**Files**: `clipd/clipboard.py:130-147`

`_get_clipboard_text()` reads `wl-paste` output without any size limit. A malicious process could fill the clipboard with gigabytes of text, which gets stored in SQLite, causing disk exhaustion or OOM.

The config has `max_image_size` (10MB) but this is never enforced for text content.

**Recommendation**: Add a max text size check:

```python
MAX_TEXT_SIZE = 10 * 1024 * 1024  # 10 MB

def _get_clipboard_text() -> str | None:
    result = subprocess.run([...], capture_output=True, text=True, timeout=2)
    if result.returncode == 0 and result.stdout:
        if len(result.stdout) > MAX_TEXT_SIZE:
            logger.warning("Clipboard content exceeds size limit, skipping")
            return None
        return result.stdout
    return None
```

---

### 5. `GetRecent` Limit Parameter Unbounded — MEDIUM

**Files**: `clipd/dbus_service.py:47`

The `limit` parameter from D-Bus is cast to `int` but not bounded. A caller can request billions of rows. While SQLite handles this gracefully, the JSON serialization of a huge result set is wasteful.

**Recommendation**: Cap at a reasonable maximum:

```python
def GetRecent(self, limit):
    limit = max(1, min(int(limit), 1000))
    ...
```

---

### 6. Pinned Clips Exempt From All Limits — MEDIUM

**Files**: `clipd/db.py` (prune logic)

Pinned clips are excluded from the `max_history` pruning. A malicious D-Bus caller could pin arbitrarily many large clips, bypassing the history limit and exhausting disk space.

**Recommendation**: Add an absolute cap on pinned clips (e.g., 100) or a total size quota.

---

### 7. Config/DB Paths Not Validated for Symlinks — MEDIUM

**Files**: `clip_common/config.py:42-63`

Neither the config file path nor the database path is checked for symlinks before opening. An attacker who can write to `~/.config/clip-manager/` could create a symlink to read or corrupt arbitrary files.

**Recommendation**: Add `Path.is_symlink()` checks before opening config or DB files.

---

### 8. `db_path` Config Accepts Arbitrary Locations — MEDIUM

**Files**: `clip_common/config.py:56`

The `db_path` TOML setting allows pointing the database anywhere on the filesystem. Combined with symlink attacks, this could be used to write SQLite data to unintended locations.

**Recommendation**: Validate that `db_path` is within `~/.local/share/clip-manager/`, or remove the config option entirely.

---

### 9. Systemd Service Has No Sandboxing — HIGH

**Files**: `clipd.service`

`systemd-analyze security clipd.service --user` scores **9.8/10 UNSAFE**. The service unit has zero hardening directives — every capability, namespace, filesystem path, and socket family is unrestricted.

The daemon only needs:
- `AF_UNIX` sockets (D-Bus session bus, X11 display)
- Read/write to `~/.local/share/clip-manager/` (SQLite DB)
- Read `~/.config/clip-manager/` (optional config)
- Execute `wl-paste`, `wl-copy`, `wtype`, `python3 -m clip_ui`
- Access to `$XDG_RUNTIME_DIR` (Wayland socket)
- X11 display access via `$DISPLAY` (XFixes)

Everything else can be locked down.

**Recommended hardened `[Service]` section**:

```ini
[Service]
Type=simple
ExecStart=%h/.local/share/clip-manager/venv/bin/python3 -m clipd
WorkingDirectory=%h
Restart=on-failure
RestartSec=3
Environment=DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 PYTHONUNBUFFERED=1

# --- Sandboxing ---

# Prevent privilege escalation
NoNewPrivileges=yes

# Restrict filesystem
ProtectSystem=strict
ProtectHome=tmpfs
BindPaths=%h/.local/share/clip-manager
BindReadOnlyPaths=%h/.config/clip-manager
# Allow access to venv and system Python/libraries
BindReadOnlyPaths=%h/.local/share/clip-manager/venv
BindReadOnlyPaths=/usr

# Restrict /proc and /dev
ProtectProc=invisible
ProcSubset=pid
PrivateDevices=yes

# Prevent kernel tampering
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectClock=yes

# Lock down namespaces and personality
RestrictNamespaces=yes
LockPersonality=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes

# Network: deny everything except UNIX sockets (D-Bus, X11)
RestrictAddressFamilies=AF_UNIX
IPAddressDeny=any

# Writable-executable memory (may need to be removed if Python JIT requires it)
MemoryDenyWriteExecute=yes

# Only native syscall ABI
SystemCallArchitectures=native

# File creation mask — owner-only by default
UMask=0077

# Tmpfiles
PrivateTmp=yes

# Drop all capabilities
CapabilityBoundingSet=
```

**Notes on compatibility**:
- `ProtectHome=tmpfs` + `BindPaths` gives the daemon access to only its specific directories under `$HOME`, not the entire home
- `RestrictAddressFamilies=AF_UNIX` blocks all network sockets (TCP/UDP) while allowing D-Bus and X11
- `IPAddressDeny=any` is a belt-and-suspenders block on network traffic
- `MemoryDenyWriteExecute=yes` may conflict with Python's `ctypes` or future JIT — test and remove if the daemon fails to start
- `BindReadOnlyPaths=/usr` is needed so the Python interpreter and system libraries remain accessible
- The service spawns `clip_ui` as a subprocess (`ToggleUI`) — this child inherits the sandbox, which is fine since it only needs D-Bus + GTK display access

**Testing**: After applying, run:
```bash
systemctl --user restart clipd
systemd-analyze security clipd.service --user
```
Target score should drop below 4.0.

---

### 10. Config File Permissions Not Enforced — MEDIUM

**Files**: `clip_common/config.py:42-63`

`load_config()` opens the config file without checking its permissions or ownership. Issues:

1. **No ownership check**: If another user can write to `~/.config/clip-manager/config.toml`, they can control `db_path`, `max_history`, and `hotkey` — potentially pointing the DB to a world-readable location or disabling pruning.

2. **No permission check**: The config file may be world-readable (default `umask 022`), leaking settings like custom `db_path`.

3. **`CLIP_MANAGER_CONFIG` env var bypass**: The `_get_config_path()` function accepts an arbitrary path from the `CLIP_MANAGER_CONFIG` environment variable with no validation. Under the current systemd service (no sandboxing), this is set by the environment, but if an attacker can influence env vars, they control the config path.

4. **No validation of parsed values**: `max_history` is cast to `int` but not bounds-checked — a value of 0 or negative would disable pruning entirely, enabling unbounded DB growth. `db_path` accepts any filesystem path after `expanduser`.

**Recommendation**:

```python
def load_config() -> Config:
    config_path = _get_config_path()
    config = Config()

    if config_path.exists():
        # Reject symlinks
        if config_path.is_symlink():
            logger.error("Config file is a symlink, ignoring: %s", config_path)
            return config

        # Warn on loose permissions
        mode = config_path.stat().st_mode
        if mode & 0o077:
            logger.warning(
                "Config file %s has permissive mode %o, should be 0600",
                config_path, mode & 0o777,
            )

        # Verify ownership
        import os
        if config_path.stat().st_uid != os.getuid():
            logger.error("Config file not owned by current user, ignoring")
            return config

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            if "max_history" in data:
                val = int(data["max_history"])
                config.max_history = max(10, min(val, 10000))

            if "db_path" in data:
                db_path = Path(os.path.expanduser(str(data["db_path"])))
                allowed_parent = Path.home() / ".local" / "share" / "clip-manager"
                if db_path.parent == allowed_parent:
                    config.db_path = str(db_path)
                else:
                    logger.error("db_path must be under %s", allowed_parent)

            ...
        except Exception:
            logger.exception("Failed to load config")

    return config
```

---

### 11. UMask Not Set — DB and Files Created World-Readable — MEDIUM

**Files**: `clipd/db.py:15`, `clipd/db.py:28`, `clipd.service`

The daemon creates directories and the SQLite database with the process's default `umask` (typically `022`), resulting in:
- `~/.local/share/clip-manager/` directory: `0755` (world-listable)
- `clips.db` file: `0644` (world-readable)
- SQLite journal/WAL files: `0644` (world-readable)

This exposes the entire clipboard history to any local user.

**Root cause**: Neither the service file nor the Python code sets a restrictive umask.

**Recommendation** (two layers):

1. **In `clipd.service`** — add `UMask=0077` (shown in finding #9). This ensures all files/dirs created by the daemon are owner-only.

2. **In `clipd/db.py`** — set umask before creating the DB directory, and `chmod` existing files:

```python
def _get_db_path() -> Path:
    old_umask = os.umask(0o077)
    try:
        data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        db_dir = Path(data_home) / "clip-manager"
        db_dir.mkdir(parents=True, exist_ok=True)
    finally:
        os.umask(old_umask)
    return db_dir / "clips.db"
```

3. **In `install.sh`** — fix existing installs:
```bash
mkdir -p -m 0700 "$INSTALL_DIR"
chmod 0700 "$INSTALL_DIR" 2>/dev/null  # fix existing
chmod 0600 "$INSTALL_DIR/clips.db" 2>/dev/null  # fix existing DB
```

---

### 12. `wl-copy` Leaks Clipboard Content in `/proc/pid/cmdline` — HIGH

**Files**: `clipd/dbus_service.py:65-68`

```python
proc = subprocess.run(
    ["wl-copy", "--", entry.content],
    timeout=2,
)
```

Clipboard content is passed as a command-line argument to `wl-copy`. While the process is alive (up to 2 seconds), any local user can read the full content via:
- `ps aux | grep wl-copy`
- `cat /proc/<pid>/cmdline`

This is a direct password leak. If a user copies a password from a password manager and then selects it from clip history, the password appears in the process table.

**Recommendation**: Pipe content via stdin instead of passing as an argument:

```python
proc = subprocess.run(
    ["wl-copy"],
    input=entry.content,
    text=True,
    timeout=2,
)
```

`wl-copy` reads from stdin when no positional argument is given. This keeps content out of `/proc/pid/cmdline`.

---

### 13. `NewClip` D-Bus Signal Broadcasts Content to Session Bus — HIGH

**Files**: `clipd/dbus_service.py:118-125`

```python
@dbus.service.signal(DBUS_INTERFACE, signature="s")
def NewClip(self, clip_json):
    pass

def emit_new_clip(self, entry: ClipEntry):
    self.NewClip(json.dumps(_entry_to_dict(entry)))
```

The `NewClip` signal emits the full clip content (including text of passwords, tokens, etc.) as a D-Bus signal. D-Bus signals are **broadcast** — any process on the session bus can subscribe with `dbus-monitor` or programmatically with `add_signal_receiver()` without any authentication.

A malicious process could silently capture every clipboard change in real time:
```bash
dbus-monitor "type='signal',interface='org.clipmanager.Daemon',member='NewClip'"
```

**Recommendation**: Either:
1. **Don't include content in the signal** — emit only the clip ID and metadata, require clients to call `GetRecent` to fetch content (at least that's a method call, not a broadcast):
   ```python
   @dbus.service.signal(DBUS_INTERFACE, signature="s")
   def NewClip(self, clip_json):
       pass

   def emit_new_clip(self, entry: ClipEntry):
       # Only emit ID and timestamp, not content
       self.NewClip(json.dumps({"id": entry.id, "timestamp": entry.timestamp}))
   ```
2. **Remove the signal entirely** if no clients currently depend on it (the UI uses `GetRecent` on launch, not signal subscription).

---

### 14. No Core Dump Protection — MEDIUM

**Files**: `clipd.service`

The service file has no `LimitCORE=0` directive. If the daemon crashes, the kernel may write a core dump containing all in-memory clipboard history (including passwords, API keys, etc.) to disk.

On Ubuntu, `apport` or `systemd-coredump` typically captures core dumps to `/var/lib/apport/coredump/` or `/var/lib/systemd/coredump/`, which may be readable by other system services or retained indefinitely.

**Recommendation**: Add to the `[Service]` section:

```ini
LimitCORE=0
```

This prevents core dump generation entirely. The daemon has no legitimate need for crash dumps in production.

---

### 15. Sensitive Data Persists in Process Memory Unscrubbed — MEDIUM

**Files**: `clipd/clipboard.py:83` (`_last_content`), `clipd/db.py` (query results), `clipd/dbus_service.py` (JSON serialization)

The daemon holds clipboard content in Python strings that are never explicitly cleared:
- `WlPasteWatcher._last_content` — retains the last clipboard text for deduplication
- D-Bus method responses — full clip history serialized to JSON strings
- SQLite row objects — remain in memory until garbage collected

Python strings are immutable and cannot be securely zeroed. Without the systemd sandboxing from finding #9, another process running as the same user could read daemon memory via `ptrace` or `/proc/<pid>/mem`.

**Recommendation**: This is inherent to Python and difficult to fully mitigate. Layers of defense:
1. **Apply systemd sandboxing** (finding #9) — this is the most effective mitigation. With `ProtectProc=invisible` and restricted capabilities, other processes cannot ptrace the daemon.
2. **Minimize retention** — set `_last_content = None` after a timeout (e.g., 30 seconds), since dedup only matters for the immediately subsequent copy.
3. **Consider `mlock`** for future work — prevents memory from being swapped to disk, though Python makes this impractical.

---

### 16. No Mechanism to Exclude Sensitive Content — MEDIUM

**Files**: `clipd/clipboard.py`, `clipd/__main__.py`

The daemon unconditionally captures and stores every clipboard change permanently. Password managers (KeePassXC, Bitwarden, 1Password) copy passwords to the clipboard, and the daemon stores them in plaintext SQLite with no expiry.

Most mature clipboard managers mitigate this:
- **`x-kde-passwordManagerHint` MIME type** — KDE/KeePassXC set this to signal "don't record"
- **Clipboard content targets** — some apps set `x-selection/clipboard-manager-ignore` as a MIME target to opt out
- **Auto-clear timeout** — delete non-pinned clips older than N hours
- **Pause capture** — a D-Bus method or UI toggle to temporarily stop recording

**Recommendation** (incremental):

1. **Check for password manager hints** before storing — query `wl-paste --list-types` and skip if the MIME types include password-related markers:
   ```python
   def _is_sensitive() -> bool:
       result = subprocess.run(
           ["wl-paste", "--list-types"],
           capture_output=True, text=True, timeout=2,
           env=_get_wlpaste_env(),
       )
       if result.returncode == 0:
           types = result.stdout.lower()
           if "password" in types or "x-kde-passwordmanagerhint" in types:
               return True
       return False
   ```

2. **Auto-expire old clips** — add a configurable `clip_ttl_hours` that deletes non-pinned clips older than the threshold on each prune cycle.

3. **Add a `PauseCapture` / `ResumeCapture` D-Bus method** — lets users or scripts temporarily stop recording.

---

### 17. Log Injection via Clipboard Content — LOW

**Files**: `clipd/clipboard.py`, `clipd/dbus_service.py`, `clip_ui/window.py`

If clipboard content ever appears in a log message (e.g., through an unexpected exception traceback that includes local variables), ANSI escape sequences in the content could:
- Manipulate terminal-based log viewers (`journalctl`, `less`, `tail`)
- Inject fake log lines via `\n` characters
- Exploit terminal emulator vulnerabilities via escape sequences

Currently, clipboard content is not intentionally logged, but `logger.exception()` calls may include local variable values in tracebacks depending on the logging configuration and Python version.

**Recommendation**:
1. Ensure clipboard content variables are never passed to `logger.*()` calls directly.
2. Add a log filter to strip control characters from log output:
   ```python
   class SanitizeFilter(logging.Filter):
       def filter(self, record):
           if isinstance(record.msg, str):
               record.msg = record.msg.translate(
                   {i: None for i in range(32) if i not in (9, 10, 13)}
               )
           return True
   ```
3. In the systemd service, `journald` already strips most ANSI by default, but direct `stderr` output (e.g., when debugging) would not be sanitized.

---

### 18. No Network Access — PASS

Grep for `socket`, `urllib`, `requests`, `http`, `smtplib`, `ftplib` found zero results. All IPC is via local session D-Bus. No telemetry, no cloud sync, no external API calls. The application is fully local-first.

---

### 19. SQL Queries Properly Parameterized — PASS

**Files**: `clipd/db.py`

All SQL queries use `?` parameter binding. No string formatting or concatenation with user input. FTS5 MATCH queries also use parameterized binding. No SQL injection vectors found.

---

### 20. Subprocess Calls Safe — PASS

**Files**: `clipd/clipboard.py`, `clipd/dbus_service.py`, `clip_ui/window.py`

All subprocess invocations use list arguments (never `shell=True`). The `wl-copy` call uses `--` to separate flags from content, preventing argument injection. Timeouts are set on `wl-paste` (2s) and `wl-copy` (2s).

**Note**: Finding #12 supersedes this for `wl-copy` specifically — while the command is not injectable, the content is visible in the process table.

---

### 21. No Code Evaluation of Clipboard Content — PASS

Clipboard content is stored as plain text in SQLite and displayed as GTK labels. No `eval()`, `exec()`, `pickle.load()`, or dynamic code execution found anywhere in the codebase.

---

### 22. Dependencies Minimal and Trustworthy — PASS

Runtime dependencies: `PyGObject` (GNOME official), `dbus-python` (freedesktop.org), `python-xlib` (X11 bindings), plus stdlib (`sqlite3`, `tomllib`). No network libraries, no heavy frameworks, no obscure PyPI packages.

---

## Additional Notes

### SQLite `check_same_thread=False`

`clipd/db.py:28` disables SQLite's thread-safety check. This is currently safe because all access is serialized through the GLib main loop (no threading). If threading is ever introduced, this would need a lock or queue.

### Systemd Service Hardening

See finding #9 for the full hardened service configuration. Current score is 9.8/10 UNSAFE per `systemd-analyze security`.

### Broad Exception Handling

Recent changes broadened `except dbus.exceptions.DBusException` to `except Exception` in `clip_ui/window.py`. This prevents CPU spin but could mask unexpected errors. Consider logging the exception type for debugging.

---

## Priority Remediation Order

**Critical — data leaks actively exploitable by local processes:**
1. **`wl-copy` stdin fix** (#12) — passwords visible in `ps aux` right now; one-line fix
2. **`NewClip` signal content removal** (#13) — every clipboard change broadcast to session bus; strip content from signal or remove it
3. **Systemd sandboxing** (#9) — service scores 9.8 UNSAFE; blocks ptrace, network, caps, namespaces, filesystem

**High — file-level privacy:**
4. **UMask + file permissions** (#2, #3, #11) — set `UMask=0077` in service, `chmod` DB/dirs to owner-only
5. **Core dump protection** (#14) — add `LimitCORE=0` to service file

**Medium — input validation and hardening:**
6. **Config file hardening** (#10) — ownership check, symlink rejection, value bounds
7. **Clipboard size limit** (#4) — prevents disk exhaustion DoS
8. **D-Bus sender validation** (#1) — defense-in-depth for session bus
9. **GetRecent limit cap** (#5) — trivial fix
10. **Pinned clip quota** (#6) — prevents storage abuse
11. **Symlink/path validation** (#7, #8) — hardening

**Longer-term — sensitive content handling:**
12. **Password manager exclusion** (#16) — check MIME types to skip passwords
13. **Auto-expire old clips** (#16) — configurable TTL for non-pinned clips
14. **Log sanitization** (#17) — strip control characters from log output
