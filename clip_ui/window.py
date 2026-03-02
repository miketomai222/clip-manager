"""GTK4 popup window for clipboard history."""

import json
import logging
import subprocess
import time

import dbus
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from clip_common.types import DBUS_BUS_NAME, DBUS_INTERFACE, DBUS_OBJECT_PATH

logger = logging.getLogger(__name__)


def _get_daemon_proxy():
    """Get a D-Bus proxy to the clip-manager daemon."""
    bus = dbus.SessionBus()
    proxy = bus.get_object(DBUS_BUS_NAME, DBUS_OBJECT_PATH)
    return dbus.Interface(proxy, DBUS_INTERFACE)


def _format_timestamp(ts: float) -> str:
    """Format a timestamp as a relative or absolute time string."""
    delta = time.time() - ts
    if delta < 60:
        return "just now"
    elif delta < 3600:
        mins = int(delta / 60)
        return f"{mins}m ago"
    elif delta < 86400:
        hours = int(delta / 3600)
        return f"{hours}h ago"
    else:
        return time.strftime("%b %d", time.localtime(ts))


class ClipRow(Gtk.Box):
    """A single row in the clip list."""

    def __init__(self, clip_data: dict):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.clip_data = clip_data

        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        # Pin indicator
        if clip_data.get("pinned"):
            pin_label = Gtk.Label(label="*")
            pin_label.add_css_class("pin-indicator")
            self.append(pin_label)

        # Content preview
        content = clip_data.get("content", "")
        # Truncate for display
        preview = content[:200].replace("\n", " ").strip()
        if len(content) > 200:
            preview += "..."

        content_label = Gtk.Label(label=preview)
        content_label.set_xalign(0)
        content_label.set_hexpand(True)
        content_label.set_ellipsize(Pango.EllipsizeMode.END)
        content_label.set_max_width_chars(80)
        self.append(content_label)

        # Timestamp
        ts = clip_data.get("timestamp", 0)
        time_label = Gtk.Label(label=_format_timestamp(ts))
        time_label.add_css_class("dim-label")
        self.append(time_label)


class ClipManagerWindow(Gtk.ApplicationWindow):
    """Main popup window for clipboard history."""

    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Clip Manager")

        self._daemon = None
        self._clips: list[dict] = []
        self._search_timeout_id = None
        self._focus_check_id = None
        self._closed = False

        # Window setup - popup style
        self.set_default_size(600, 450)
        self.set_resizable(False)
        self.set_decorated(False)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(vbox)

        # Search entry
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search clips...")
        self._search_entry.set_margin_start(8)
        self._search_entry.set_margin_end(8)
        self._search_entry.set_margin_top(8)
        self._search_entry.set_margin_bottom(4)
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_entry.connect("activate", self._on_search_activate)
        # stop-search is dead code — key controller (CAPTURE phase) consumes Escape first
        vbox.append(self._search_entry)

        # Scrolled window for clip list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        vbox.append(scrolled)

        # List box
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self._listbox)

        # Key controller for keyboard navigation
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        # Focus controller - close on focus loss
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("leave", self._on_focus_leave)
        self.add_controller(focus_controller)

        # Load CSS
        self._load_css()

        # Load clips
        GLib.idle_add(self._load_clips)

        # Focus the search entry (wrap in lambda: grab_focus returns True, which
        # would cause idle_add to re-schedule it on every main loop iteration)
        GLib.idle_add(lambda: self._search_entry.grab_focus() and False)

    def _load_css(self):
        css = b"""
        window {
            background-color: @theme_bg_color;
            border: 1px solid @borders;
            border-radius: 8px;
        }
        .dim-label {
            opacity: 0.6;
            font-size: 0.85em;
        }
        .pin-indicator {
            color: @accent_color;
            font-weight: bold;
        }
        listbox row:selected {
            background-color: alpha(@accent_color, 0.2);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _get_daemon(self):
        if self._daemon is None:
            try:
                self._daemon = _get_daemon_proxy()
            except Exception:
                logger.error("Cannot connect to clip-manager daemon")
        return self._daemon

    def _load_clips(self):
        """Load recent clips from the daemon."""
        daemon = self._get_daemon()
        if not daemon:
            return False

        try:
            result = daemon.GetRecent(dbus.UInt32(50))
            self._clips = json.loads(str(result))
            self._populate_list(self._clips)
        except Exception:
            logger.exception("Failed to load clips")
        return False  # Never repeat

    def _search_clips(self, query: str):
        """Search clips via daemon."""
        daemon = self._get_daemon()
        if not daemon:
            return

        try:
            if query:
                result = daemon.Search(query)
            else:
                result = daemon.GetRecent(dbus.UInt32(50))
            clips = json.loads(str(result))
            self._populate_list(clips)
        except Exception:
            logger.exception("Failed to search clips")

    def _populate_list(self, clips: list[dict]):
        """Populate the list box with clip rows."""
        # Remove existing rows
        while True:
            row = self._listbox.get_row_at_index(0)
            if row is None:
                break
            self._listbox.remove(row)

        for clip in clips:
            row = ClipRow(clip)
            self._listbox.append(row)

        # Select first row
        first_row = self._listbox.get_row_at_index(0)
        if first_row:
            self._listbox.select_row(first_row)

    def _on_search_changed(self, entry):
        """Handle search text changes with debounce."""
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
        self._search_timeout_id = GLib.timeout_add(
            150, self._do_search, entry.get_text()
        )

    def _on_search_activate(self, entry):
        """Handle Enter in the search entry — select the highlighted clip."""
        selected = self._listbox.get_selected_row()
        if selected:
            self._on_row_activated(self._listbox, selected)

    def _do_search(self, query: str):
        self._search_timeout_id = None
        self._search_clips(query)
        return False  # Don't repeat

    def _on_row_activated(self, listbox, row):
        """Handle row activation (Enter or click)."""
        if row is None:
            return
        clip_row = row.get_child()
        if isinstance(clip_row, ClipRow):
            self._select_clip(clip_row.clip_data)

    def _close_window(self):
        """Mark the window closed and destroy it."""
        self._closed = True
        self.close()

    def _copy_clip_to_clipboard(self, clip_id: int):
        """Tell the daemon to put clip_id on the clipboard."""
        daemon = self._get_daemon()
        if daemon:
            try:
                daemon.SelectEntry(dbus.UInt32(clip_id))
            except Exception:
                logger.exception("Failed to select clip")

    def _select_clip(self, clip_data: dict):
        """Select a clip: set clipboard and paste."""
        self._copy_clip_to_clipboard(clip_data["id"])
        self._close_window()

        # Small delay to let focus return, then simulate Ctrl+V
        GLib.timeout_add(150, self._simulate_paste)

    def _simulate_paste(self):
        """Simulate Ctrl+V using wtype."""
        try:
            subprocess.Popen(
                ["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("wtype not found. Install wtype for paste simulation.")
        return False  # Don't repeat

    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard shortcuts."""
        if keyval == Gdk.KEY_Escape:
            self._close_window()
            return True

        if keyval == Gdk.KEY_c and state & Gdk.ModifierType.CONTROL_MASK:
            selected = self._listbox.get_selected_row()
            if selected:
                clip_row = selected.get_child()
                if isinstance(clip_row, ClipRow):
                    self._copy_clip_to_clipboard(clip_row.clip_data["id"])
            self._close_window()
            return True

        # Arrow keys move selection in list
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            selected = self._listbox.get_selected_row()
            if selected is None:
                idx = 0
            else:
                idx = selected.get_index()
                if keyval == Gdk.KEY_Down:
                    idx += 1
                else:
                    idx -= 1

            target_row = self._listbox.get_row_at_index(idx)
            if target_row:
                self._listbox.select_row(target_row)
                target_row.grab_focus()
            return True

        # Enter on selected row
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = self._listbox.get_selected_row()
            if selected:
                self._on_row_activated(self._listbox, selected)
            return True

        return False

    def _on_focus_leave(self, controller):
        """Close window when it loses focus."""
        if self._closed:
            return
        # Guard against multiple pending checks
        if self._focus_check_id is not None:
            return
        self._focus_check_id = GLib.timeout_add(100, self._check_focus)

    def _check_focus(self):
        self._focus_check_id = None
        if self._closed:
            return False
        if not self.is_active():
            self._close_window()
        return False
