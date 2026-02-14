"""
Login window for OMOMatrix.
"""

import asyncio
import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, GObject

logger = logging.getLogger(__name__)


class LoginWindow(Adw.Window):
    """Login window for entering Matrix credentials."""
    
    __gsignals__ = {
        'login-success': (GObject.SignalFlags.RUN_FIRST, None, ())
    }
    
    def __init__(self, application):
        """Initialize login window.
        
        Args:
            application: The main application instance
        """
        super().__init__(application=application)
        
        self.app = application
        self.set_default_size(400, 500)
        self.set_title("OMOMatrix - Login")
        
        # Create UI
        self._build_ui()
    
    def _build_ui(self):
        """Build the login window UI."""
        # Main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_valign(Gtk.Align.CENTER)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_spacing(20)
        main_box.set_margin_top(40)
        main_box.set_margin_bottom(40)
        main_box.set_margin_start(40)
        main_box.set_margin_end(40)
        
        # App icon/title
        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='bold'>OMOMatrix</span>")
        main_box.append(title)
        
        subtitle = Gtk.Label(label="Modern Matrix Client")
        subtitle.add_css_class("dim-label")
        main_box.append(subtitle)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 20)
        main_box.append(spacer)
        
        # Login form
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        form.set_spacing(12)
        
        # Homeserver entry
        self.homeserver_entry = Adw.EntryRow()
        self.homeserver_entry.set_title("Homeserver")
        self.homeserver_entry.set_text("https://matrix.org")
        form.append(self.homeserver_entry)
        
        # Username entry
        self.username_entry = Adw.EntryRow()
        self.username_entry.set_title("Username")
        form.append(self.username_entry)
        
        # Password entry
        self.password_entry = Adw.PasswordEntryRow()
        self.password_entry.set_title("Password")
        form.append(self.password_entry)
        
        # Add form to a clamp for better centering
        clamp = Adw.Clamp()
        clamp.set_maximum_size(400)
        clamp.set_child(form)
        main_box.append(clamp)
        
        # Error label
        self.error_label = Gtk.Label()
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)
        main_box.append(self.error_label)
        
        # Login button
        self.login_button = Gtk.Button(label="Login")
        self.login_button.add_css_class("suggested-action")
        self.login_button.add_css_class("pill")
        self.login_button.set_size_request(120, -1)
        self.login_button.connect('clicked', self.on_login_clicked)
        
        button_box = Gtk.Box()
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.append(self.login_button)
        main_box.append(button_box)
        
        # Spinner (hidden by default)
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        main_box.append(self.spinner)
        
        # Set main content
        self.set_content(main_box)
    
    def on_login_clicked(self, _button):
        """Handle login button click."""
        homeserver = self.homeserver_entry.get_text().strip()
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()
        
        # Validate inputs
        if not homeserver or not username or not password:
            self.show_error("Please fill in all fields")
            return
        
        # Disable button and show spinner
        self.login_button.set_sensitive(False)
        self.spinner.set_visible(True)
        self.spinner.start()
        self.error_label.set_visible(False)
        
        # Perform login asynchronously
        # Use application loop explicitly
        self.app.loop.create_task(self._do_login(homeserver, username, password))
    
    async def _do_login(self, homeserver: str, username: str, password: str):
        """Perform the login operation.
        
        Args:
            homeserver: Matrix homeserver URL
            username: Username
            password: Password
        """
        try:
            # Set homeserver
            self.app.matrix_client.homeserver = homeserver
            
            # Attempt login
            success = await self.app.matrix_client.login(username, password)
            
            if success:
                GLib.idle_add(self._on_login_success)
            else:
                GLib.idle_add(self.show_error, "Login failed. Check your credentials.")
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            GLib.idle_add(self.show_error, f"Error: {str(e)}")
    
    def _on_login_success(self):
        """Called on successful login."""
        self.spinner.stop()
        self.spinner.set_visible(False)
        self.emit('login-success')
    
    def show_error(self, message: str):
        """Show error message.
        
        Args:
            message: Error message to display
        """
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
        self.login_button.set_sensitive(True)
        self.spinner.stop()
        self.spinner.set_visible(False)
