"""
Member list sidebar view.
"""

import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gdk, GLib

logger = logging.getLogger(__name__)


class MemberListView(Gtk.Box):
    """Sidebar view showing room members."""
    
    def __init__(self, application, matrix_client):
        """Initialize member list view.
        
        Args:
            application: The main application instance
            matrix_client: MatrixClient instance
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        
        self.app = application
        self.matrix_client = matrix_client
        self.avatar_manager = application.avatar_manager
        self.current_room_id = None
        self.member_rows = {} # user_id -> row widget
        
        self.add_css_class("sidebar")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the member list UI."""
        # Header
        header = Gtk.Label(label="Members")
        header.add_css_class("title-4")
        header.set_margin_top(12)
        header.set_margin_bottom(8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        self.append(header)
        
        # Scrollable member list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # ListBox for members
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("navigation-sidebar")
        
        scrolled.set_child(self.list_box)
        self.append(scrolled)
    
    def set_room(self, room_id: str):
        """Set the current room and load members.
        
        Args:
            room_id: Room ID
        """
        self.current_room_id = room_id
        self.load_members()
    
    def load_members(self):
        """Load members for the current room."""
        if not self.current_room_id:
            return
            
        rooms = self.matrix_client.get_rooms()
        if self.current_room_id not in rooms:
            return
            
        room = rooms[self.current_room_id]
        current_members = set(room.users.keys())
        existing_members = set(self.member_rows.keys())
        
        # Remove left members
        to_remove = existing_members - current_members
        for uid in to_remove:
            row = self.member_rows.pop(uid)
            self.list_box.remove(row)
            
        # Add or update members
        for user_id in current_members:
            display_name = room.user_name(user_id) or user_id
            avatar_url = room.users[user_id].avatar_url
            
            if user_id in self.member_rows:
                # Update (could update name/avatar if changed)
                # For now just update name
                self._update_member_row(user_id, display_name)
            else:
                row = self._create_member_row(user_id, display_name, avatar_url)
                self.member_rows[user_id] = row
                self.list_box.append(row)

    def _update_member_row(self, user_id, display_name):
        """Update an existing member row."""
        row = self.member_rows.get(user_id)
        if not row:
            return
        if hasattr(row, 'name_label') and row.name_label.get_text() != display_name:
            row.name_label.set_text(display_name)

    def _create_member_row(self, user_id: str, display_name: str, avatar_url: Optional[str] = None) -> Gtk.ListBoxRow:
        """Create a list box row for a member.
        
        Args:
            user_id: Matrix user ID
            display_name: User's display name
            avatar_url: Optional avatar URL
            
        Returns:
            ListBoxRow widget
        """
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Avatar
        avatar_bin = Gtk.Box()
        avatar_bin.set_size_request(32, 32)
        avatar_bin.add_css_class("member-avatar")
        
        avatar_widget = Adw.Avatar.new(32, display_name, True)
        avatar_bin.append(avatar_widget)
        box.append(avatar_bin)
        
        # Display name
        name_label = Gtk.Label(label=display_name)
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3)  # ELLIPSIZE_END
        name_label.set_hexpand(True)
        box.append(name_label)
        
        row.set_child(box)
        # Store references
        row.name_label = name_label
        row.avatar_image = avatar_widget
        
        # Load avatar
        self.app.loop.create_task(
            self._resolve_and_load_member_avatar(user_id, avatar_widget, avatar_url, name_label)
        )
        
        return row

    async def _resolve_and_load_member_avatar(self, user_id, avatar_widget, avatar_url, name_label):
        """Resolve and load member avatar."""
        if not avatar_url:
            profile = await self.matrix_client.get_user_profile(user_id)
            if profile:
                avatar_url = profile.get("avatar_url")
                new_name = profile.get("displayname")
                if new_name:
                    GLib.idle_add(name_label.set_text, new_name)
                    GLib.idle_add(avatar_widget.set_text, new_name)
        
        # Ensure fallback text is always set
        if not avatar_url:
            GLib.idle_add(avatar_widget.set_text, name_label.get_text())
                    
        if avatar_url:
            try:
                path = await self.avatar_manager.get_avatar(
                    self.matrix_client.homeserver,
                    avatar_url,
                    size=32,
                    access_token=self.matrix_client.client.access_token
                )
                if path:
                    def update_avatar():
                        try:
                            texture = Gdk.Texture.new_from_filename(str(path))
                            avatar_widget.set_custom_image(texture)
                        except Exception as e:
                            logger.error(f"Failed to create texture from {path}: {e}")
                    
                    GLib.idle_add(update_avatar)
            except Exception as e:
                logger.error(f"Error loading member avatar: {e}")
