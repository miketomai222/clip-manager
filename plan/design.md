# Clip Manager - Design Decisions

A clipboard manager for Ubuntu, inspired by [Ditto](https://github.com/sabrogden/Ditto).

---

## 1. Language & Framework

| Option | Pros | Cons |
|---|---|---|
| **Python + GTK** | Native GNOME look & feel; fast to prototype; excellent GI bindings for GTK4, GLib, GDK; easy clipboard and D-Bus access; large ecosystem | Slower than compiled languages; packaging/distribution is messier; GIL limits concurrency |
| **Rust + GTK (gtk4-rs)** | Native look & feel; excellent performance and memory safety; strong async story with tokio; produces a single binary | Steeper learning curve; slower iteration; GTK4 Rust bindings are less documented than Python |
| **Python + Qt (PyQt6/PySide6)** | Rich widget set; good cross-desktop look; mature clipboard API; QSystemTrayIcon built-in | Heavier dependency; Qt licensing (GPL/LGPL vs commercial); less native on GNOME |
| **Tauri (Rust + Webview)** | Modern web-based UI; lightweight (~5MB); Rust backend for performance; easy to make pretty | Extra complexity bridging frontend/backend; clipboard monitoring still needs native code; web UI may feel out of place |
| **Electron** | Easiest UI development (HTML/CSS/JS); huge ecosystem | Heavy resource usage (~100MB+ RAM); feels out of place on Linux; overkill for this |

**Recommendation:** Python + GTK for fastest path to a working tool. Rust + GTK if performance and long-term maintainability matter more.

---

## 2. Display Server Support

| Option | Pros | Cons |
|---|---|---|
| **Wayland only** | Modern, secure; default on Ubuntu 22.04+; simpler codebase | Cannot use X11 clipboard tricks; global hotkeys require a portal or compositor-specific protocol; clipboard monitoring is more restricted (no passive snooping) |
| **X11 only** | Easiest clipboard monitoring (XFixes); global hotkeys trivial (XGrabKey); mature tooling | Legacy; Ubuntu is moving away from it; won't work on Wayland sessions |
| **Both (Wayland + X11)** | Maximum compatibility; works regardless of session type | Need abstraction layer; two code paths for clipboard monitoring, hotkeys, and window focus; more testing surface |

### Wayland-specific challenges
- **Clipboard access:** Wayland only gives clipboard access to the focused window. Workarounds: `wl-clipboard`, portals, or running as a background service with compositor extensions.
- **Global hotkeys:** No protocol for global shortcuts in base Wayland. Options: `xdg-desktop-portal` (GNOME 41+), compositor-specific (KDE has shortcuts portal), or D-Bus.
- **Paste to previous window:** Wayland doesn't let you programmatically focus/type into another window. Options: `xdotool` (X11 only), `ydotool` (Wayland), `wtype`, or portal-based input simulation.

**Recommendation:** Target Wayland-first with X11 fallback, since Ubuntu defaults to Wayland.

---

## 3. Clipboard Content Types

| Option | Storage needs | Complexity | Notes |
|---|---|---|---|
| **Text only** | Minimal (SQLite text column) | Low | Plain text + rich text (HTML). Covers 90% of use cases. |
| **Text + Images** | Moderate (BLOBs or file-backed) | Medium | Need to handle PNG/JPEG clipboard targets; thumbnail generation for UI; storage grows fast |
| **All formats** | High (arbitrary MIME blobs) | High | Text, images, HTML, URIs, files, custom app formats. Need to store MIME type + raw bytes. Like Ditto's full support. |

### Storage considerations
- Images can be large; storing in SQLite BLOBs works up to ~1MB, beyond that file-backed with DB metadata is better.
- Need a max history size / max entry size policy to prevent runaway disk usage.
- Consider deduplication (don't store the same text string twice in a row).

**Recommendation:** Start with Text + Images, design the storage layer to be extensible to all formats.

---

## 4. Core Features (Priority Tiers)

### Tier 1 - MVP
- [ ] Clipboard monitoring (detect new clipboard content automatically)
- [ ] Persistent history stored in a local database
- [ ] Search/filter history (substring match)
- [ ] Global hotkey to open popup window
- [ ] Select an entry to paste it into the previously active window
- [ ] System tray icon with basic menu
- [ ] Configurable max history size

### Tier 2 - Usable daily driver
- [ ] Pinned / starred clips (survive history pruning)
- [ ] Groups / folders to organize saved clips
- [ ] Rich preview (show images, formatted HTML)
- [ ] Keyboard-driven navigation (arrow keys, type-to-search, Enter to paste)
- [ ] Multi-paste (select multiple entries, paste in sequence)
- [ ] Paste as plain text option (strip formatting)
- [ ] Configurable hotkey
- [ ] Autostart on login

### Tier 3 - Power features
- [ ] Network sync between machines (LAN or cloud)
- [ ] Regex search
- [ ] Clip transformations (uppercase, trim, URL encode, etc.)
- [ ] Scripting / plugins
- [ ] Statistics (most used clips, copy frequency)
- [ ] Ignore list (don't record from specific apps)
- [ ] Sensitive content detection (don't record passwords)

---

## 5. Additional Design Questions

### 5a. Storage Backend

| Option | Pros | Cons |
|---|---|---|
| **SQLite** | Zero-config; single file; great for local data; FTS5 for full-text search | Not ideal for large BLOBs; single-writer |
| **Plain files (JSON/YAML)** | Simple; human-readable; easy to debug | Slow search at scale; no indexing; fragile |
| **LevelDB / RocksDB** | Fast key-value lookups; handles binary well | No SQL; harder to query; extra dependency |

**Recommendation:** SQLite with FTS5. Battle-tested for this kind of local app.

---

### 5b. UI Style for the Popup

| Option | Description |
|---|---|
| **Vertical list (Ditto-style)** | Scrollable list with preview of each entry; search bar at top. Familiar, proven UX. |
| **Grid / tile view** | Better for image-heavy clipboard usage; less text density. |
| **Rofi/dmenu-style** | Minimal launcher-style popup; keyboard-first; no window chrome. Feels native to tiling WM users. |
| **Hybrid** | List view for text, grid for images; toggle between them. |

---

### 5c. Daemon Architecture

| Option | Description |
|---|---|
| **Single process** | One app does everything: monitors clipboard, serves UI, manages DB. Simpler but UI blocks monitoring if it hangs. |
| **Daemon + UI client** | Separate background service (systemd user unit) for clipboard monitoring + DB. Separate UI process launched on hotkey. More robust, cleaner separation. |
| **D-Bus service** | Daemon exposes a D-Bus API. UI (or third-party tools) communicate via D-Bus. Most extensible. |

**Recommendation:** Daemon + UI client with D-Bus communication. The daemon runs as a systemd user service, monitors the clipboard, and stores entries. The UI is a lightweight popup spawned on hotkey.

---

### 5d. Hotkey Registration

| Option | Wayland | X11 | Notes |
|---|---|---|---|
| **xdg-desktop-portal GlobalShortcuts** | Yes (GNOME 41+) | N/A | Standards-based; requires user consent dialog |
| **D-Bus to GNOME Shell** | Yes | Yes | GNOME-specific; fragile across versions |
| **XGrabKey** | No | Yes | Classic X11 approach; doesn't work on Wayland |
| **Keybind in desktop settings** | Yes | Yes | User manually binds a key to launch the UI via GNOME/KDE settings. Most reliable but requires user setup. |
| **ydotool / global-shortcuts compositor protocol** | Partial | N/A | Compositor-dependent |

---

### 5e. Paste Mechanism (Simulating paste into the target window)

| Option | Wayland | X11 | Notes |
|---|---|---|---|
| **Set clipboard + simulate Ctrl+V** | Yes (via wtype/ydotool) | Yes (via xdotool) | Most common approach; requires input simulation tool |
| **XDoTool type** | No | Yes | Directly types text; only works for text; X11 only |
| **wtype** | Yes | No | Wayland equivalent of xdotool type |
| **Primary selection (middle-click)** | Yes | Yes | Works but unusual UX; only for text |

---

### 5f. Packaging & Distribution

| Option | Pros | Cons |
|---|---|---|
| **Flatpak** | Sandboxed; easy install; auto-updates | Clipboard/hotkey access may be restricted by sandbox |
| **Snap** | Ubuntu-native; auto-updates | Same sandboxing concerns; snap overhead |
| **PPA / .deb** | Full system access; native feel | Maintenance burden; distro-specific |
| **.AppImage** | Single file; no install needed | No auto-updates; no desktop integration by default |
| **pip install** | Trivial for Python projects | Doesn't handle desktop integration (autostart, tray, etc.) |

---

### 5g. Configuration

| Option | Description |
|---|---|
| **TOML/YAML config file** | `~/.config/clip-manager/config.toml`. Simple, human-editable. |
| **GSettings / dconf** | Native GNOME way. Integrates with `gnome-tweaks` and `dconf-editor`. |
| **GUI settings window** | In-app preferences dialog. More accessible but more code. |

---

## 6. Open Questions (Need Your Input)

1. **What Ubuntu version are you on?** (Determines Wayland maturity, GTK version, portal availability)
2. **Do you use GNOME, KDE, or another desktop environment?** (Affects hotkey registration, tray icon, theming)
3. **Do you use a tiling WM or the default GNOME shell?** (Affects popup positioning and UI style preference)
4. **How large should the history be by default?** (Ditto defaults to 500 entries)
5. **Do you need it to survive reboots?** (Persistent DB vs in-memory only)
6. **Is network sync between machines important, or is this single-machine only?**
7. **Do you have a preferred hotkey in mind?** (Ditto uses Ctrl+`, common alternatives: Super+V, Ctrl+Shift+V)
8. **Should it integrate with existing tools?** (e.g., work alongside `gpaste`, expose a CLI, provide a Rofi mode)
9. **What's your Python/Rust experience level?** (Affects tech stack recommendation)
10. **Is this for personal use or do you plan to distribute it?** (Affects packaging priority)
