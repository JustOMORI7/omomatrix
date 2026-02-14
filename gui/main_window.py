"""
Main application window for OMOMatrix.
"""

import asyncio
import logging
import time
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib

from .room_list import RoomListView
from .message_view import MessageView
from .member_list import MemberListView

logger = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main application window with three-column layout."""
    
    def __init__(self, application, matrix_client, avatar_manager):
        """Initialize main window.
        
        Args:
            application: The main application instance
            matrix_client: MatrixClient instance
            avatar_manager: AvatarManager instance
        """
        super().__init__(application=application)
        
        self.app = application
        self.matrix_client = matrix_client
        self.avatar_manager = avatar_manager
        self.current_room_id = None
        self._last_sync_time = 0
        
        self.set_default_size(1200, 800)
        self.set_title("OMOMatrix")
        
        # Set icon
        try:
            from gi.repository import Gdk
            texture = Gdk.Texture.new_from_filename("/home/omori/omomatrix/icon.png")
            self.set_icon_name("omomatrix") # For theme engines
            # In some GTK4 versions we might need a different way, 
            # but usually setting the icon on the window or application is enough.
        except Exception as e:
            logger.error(f"Failed to set MainWindow icon: {e}")
        
        # Build UI
        self._build_ui()
        
        # Set up callbacks
        self.matrix_client.on_sync = self.on_sync
    
    def on_sync(self, response=None):
        """Called when Matrix sync completes."""
        logger.debug(f"on_sync callback triggered with response: {type(response).__name__ if response else 'None'}")
        
        # MessageView handles its own events directly via client callbacks,
        # but RoomListView needs the sync response to update unread counts/ordering.
        # We no longer throttle RoomList updates because they are now incremental and fast.
        if response:
            self.room_list.refresh_rooms(response)
        else:
            # Initial sync or force refresh
            self.room_list.refresh_rooms(None)

    def _build_ui(self):
        """Build the main window UI."""
        # Header bar
        header = Adw.HeaderBar()
        
        # Member list toggle button
        self.member_toggle = Gtk.ToggleButton()
        self.member_toggle.set_icon_name("system-users-symbolic")
        self.member_toggle.set_tooltip_text("Toggle Member List")
        self.member_toggle.set_active(True)
        self.member_toggle.connect('toggled', self.on_member_toggle)
        header.pack_end(self.member_toggle)
        
        # Logout button
        logout_btn = Gtk.Button()
        logout_btn.set_icon_name("system-log-out-symbolic")
        logout_btn.set_tooltip_text("Logout")
        logout_btn.connect('clicked', self.on_logout_clicked)
        header.pack_end(logout_btn)
        
        # Main content area
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)
        
        # Three-column paned layout
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_vexpand(True)
        
        # Left sidebar - Room list
        # Pass app to RoomListView for async task creation
        self.room_list = RoomListView(self.app, self.matrix_client)
        self.room_list.set_size_request(280, -1)
        self.room_list.connect('room-selected', self.on_room_selected)
        
        # Center - Message view
        # Pass app to MessageView for async task creation
        self.message_view = MessageView(self.app, self.matrix_client, self.avatar_manager)
        
        # Right sidebar - Member list
        self.member_list = MemberListView(self.app, self.matrix_client)
        self.member_list.set_size_request(250, -1)
        
        # Create secondary paned for message view + member list
        message_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        message_paned.set_start_child(self.message_view)
        message_paned.set_end_child(self.member_list)
        message_paned.set_resize_start_child(True)
        message_paned.set_shrink_start_child(False)
        message_paned.set_resize_end_child(False)
        message_paned.set_shrink_end_child(False)
        
        # Add to main paned
        self.paned.set_start_child(self.room_list)
        self.paned.set_end_child(message_paned)
        self.paned.set_resize_start_child(False)
        self.paned.set_shrink_start_child(False)
        
        main_box.append(self.paned)
        self.set_content(main_box)
        
        GLib.idle_add(self.room_list.refresh_rooms)
    
    def on_room_selected(self, _widget, room_id: str):
        """Handle room selection.
        
        Args:
            room_id: Selected room ID
        """
        logger.info(f"Room selected: {room_id}")
        self.current_room_id = room_id
        
        # Update views
        self.message_view.set_room(room_id)
        self.member_list.set_room(room_id)
    
    def on_member_toggle(self, button):
        """Handle member list toggle.
        
        Args:
            button: Toggle button
        """
        visible = button.get_active()
        self.member_list.set_visible(visible)
    
    def on_logout_clicked(self, _button):
        """Handle logout button click."""
        # Show confirmation dialog
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading("Logout")
        dialog.set_body("Are you sure you want to logout?")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("logout", "Logout")
        dialog.set_response_appearance("logout", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self.on_logout_response)
        dialog.present()
    
    def on_logout_response(self, dialog, response):
        """Handle logout confirmation response.
        
        Args:
            dialog: The dialog
            response: Response ID
        """
        if response == "logout":
            self.app.loop.create_task(self._do_logout())
    
    async def _do_logout(self):
        """Perform logout operation."""
        await self.matrix_client.logout()
        
        # Close main window and show login
        GLib.idle_add(self._show_login_after_logout)
    
    def _show_login_after_logout(self):
        """Show login window after logout."""
        self.close()
        self.app.main_window = None
        self.app.show_login_window()
