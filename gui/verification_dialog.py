"""
Interactive E2EE Device Verification Dialog (SAS).
"""

import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, GObject

logger = logging.getLogger(__name__)

class VerificationDialog(Adw.Window):
    """Dialog for SAS emoji verification."""
    
    def __init__(self, parent, matrix_client, loop, transaction_id, other_user_id):
        super().__init__(transient_for=parent, modal=True)
        
        self.client = matrix_client
        self.loop = loop
        self.tx_id = transaction_id
        self.user_id = other_user_id
        
        self.set_default_size(450, 400)
        self.set_title("Device Verification")
        
        self._build_ui()
        
    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        
        # Title/Info
        title_label = Gtk.Label()
        title_label.set_markup(f"<span size='large' weight='bold'>Verify with {self.user_id}</span>")
        main_box.append(title_label)
        
        self.status_label = Gtk.Label(label="Waiting for other device...")
        self.status_label.add_css_class("dim-label")
        main_box.append(self.status_label)
        
        # Emoji container
        self.emoji_box = Gtk.FlowBox()
        self.emoji_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.emoji_box.set_valign(Gtk.Align.CENTER)
        self.emoji_box.set_halign(Gtk.Align.CENTER)
        self.emoji_box.set_min_children_per_line(7)
        self.emoji_box.set_max_children_per_line(7)
        self.emoji_box.set_row_spacing(12)
        self.emoji_box.set_column_spacing(12)
        main_box.append(self.emoji_box)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.CENTER)
        
        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.connect("clicked", self.on_cancel_clicked)
        button_box.append(self.cancel_btn)
        
        self.confirm_btn = Gtk.Button(label="They Match")
        self.confirm_btn.add_css_class("suggested-action")
        self.confirm_btn.set_sensitive(False)
        self.confirm_btn.connect("clicked", self.on_confirm_clicked)
        button_box.append(self.confirm_btn)
        
        main_box.append(button_box)
        self.set_content(main_box)

    def show_emojis(self, emojis):
        """Display the verification emojis."""
        self.status_label.set_text("Do these emojis match the other device?")
        
        # Clear box
        while (child := self.emoji_box.get_first_child()):
            self.emoji_box.remove(child)
            
        for emoji, name in emojis:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            
            icon_label = Gtk.Label()
            icon_label.set_markup(f"<span size='xx-large'>{emoji}</span>")
            vbox.append(icon_label)
            
            name_label = Gtk.Label(label=name.capitalize())
            name_label.set_ellipsize(3) # ELLIPSIZE_END
            name_label.set_max_width_chars(10)
            vbox.append(name_label)
            
            self.emoji_box.append(vbox)
            
        self.confirm_btn.set_sensitive(True)

    def on_confirm_clicked(self, btn):
        self.status_label.set_text("Verification successful!")
        self.confirm_btn.set_sensitive(False)
        self.loop.create_task(self.client.confirm_sas(self.tx_id))
        GLib.timeout_add(2000, self.close)

    def on_cancel_clicked(self, btn):
        self.loop.create_task(self.client.cancel_verification(self.tx_id))
        self.close()
