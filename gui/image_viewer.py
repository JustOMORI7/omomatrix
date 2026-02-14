import logging
import gi
from pathlib import Path

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gdk, Gio, GLib

logger = logging.getLogger(__name__)

class ImageViewer(Adw.Window):
    """Full-screen image viewer for Matrix messages."""
    
    def __init__(self, parent_window, image_path, title="Image Viewer"):
        """Initialize the viewer.
        
        Args:
            parent_window: The main window to set as transient for
            image_path: Path to the local image file
            title: Window title
        """
        super().__init__(transient_for=parent_window)
        
        self.set_title(title)
        self.set_default_size(800, 600)
        self.maximize()
        self.add_css_class("image-viewer-window")
        
        # Overlay for content and controls
        overlay = Gtk.Overlay()
        self.set_content(overlay)
        
        # Scrolled window for panning
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        overlay.set_child(scrolled)
        
        # Image display
        self.picture = Gtk.Picture()
        self.picture.set_keep_aspect_ratio(True)
        self.picture.set_can_shrink(True)
        self.picture.add_css_class("viewer-image")
        
        if image_path:
            gfile = Gio.File.new_for_path(str(image_path))
            self.picture.set_file(gfile)
        
        scrolled.set_child(self.picture)
        
        # Close button in top-right
        close_button = Gtk.Button()
        close_button.set_icon_name("window-close-symbolic")
        close_button.add_css_class("circular")
        close_button.add_css_class("viewer-close-button")
        close_button.set_halign(Gtk.Align.END)
        close_button.set_valign(Gtk.Align.START)
        close_button.set_margin_top(20)
        close_button.set_margin_end(20)
        close_button.connect("clicked", lambda _: self.close())
        overlay.add_overlay(close_button)
        
        # ESC key to close
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
        
    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle key presses."""
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
