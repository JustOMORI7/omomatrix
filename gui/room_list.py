"""
Room list sidebar view with space support.
"""

import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gdk, GObject, GLib

logger = logging.getLogger(__name__)


class RoomListView(Gtk.Box):
    """Sidebar view showing rooms organized by spaces."""
    
    __gsignals__ = {
        'room-selected': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }
    
    def __init__(self, application, matrix_client):
        """Initialize room list view.
        
        Args:
            application: The main application instance
            matrix_client: MatrixClient instance
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        
        self.app = application
        self.matrix_client = matrix_client
        self.avatar_manager = application.avatar_manager
        self.selected_room = None
        
        self.all_list_boxes = [] # Keep track of all ListBox widgets for selection sync
        self.room_rows = {} # room_id -> row widget (for updates)
        self.expander_states = {} # space_id -> expanded (bool)
        
        self.add_css_class("sidebar")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the room list UI."""
        # Header with search
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header_box.set_spacing(6)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(12)
        header_box.set_margin_start(12)
        header_box.set_margin_end(12)
        
        # Search entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search rooms...")
        header_box.append(self.search_entry)
        
        self.append(header_box)
        
        # Scrollable room list
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # Main container for expanders
        self.main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.scrolled.set_child(self.main_container)
        self.append(self.scrolled)
        
        # Join room button
        join_button = Gtk.Button(label="Join Room")
        join_button.set_margin_top(6)
        join_button.set_margin_bottom(6)
        join_button.set_margin_start(12)
        join_button.set_margin_end(12)
        join_button.connect('clicked', self.on_join_clicked)
        self.append(join_button)

    def refresh_rooms(self, response=None):
        """Refresh the room list hierarchy."""
        # For now, we do a full rebuild on hierarchy changes
        # In a real app we'd want to be more surgical
        logger.debug("Refreshing room list hierarchy")
        
        hierarchy = self.matrix_client.get_hierarchy()
        rooms = self.matrix_client.get_rooms()
        
        # Clear existing content
        while (child := self.main_container.get_first_child()):
            self.main_container.remove(child)
        
        self.all_list_boxes = []
        self.room_rows = {}
        
        # 1. Add top-level spaces
        for space_id in hierarchy["top_level_spaces"]:
            room = rooms.get(space_id)
            if room:
                expander = self._create_space_expander(space_id, room, hierarchy, rooms)
                self.main_container.append(expander)
        
        # 2. Add Orphans section (Rooms & DMs)
        if hierarchy["orphans"]:
            orphans_expander = self._create_orphans_expander(hierarchy["orphans"], rooms)
            self.main_container.append(orphans_expander)
            
    def _create_space_expander(self, space_id, room, hierarchy, rooms, depth=0):
        """Create an expander for a space and its children."""
        expander = Gtk.Expander()
        # Visual indentation for nested spaces
        expander.set_margin_start(8 if depth > 0 else 0)
        
        # Expander header (the space itself)
        header_box = self._create_room_item_widget(space_id, room)
        expander.set_label_widget(header_box)
        
        # Restore expanded state
        is_expanded = self.expander_states.get(space_id, False)
        expander.set_expanded(is_expanded)
        expander.connect('notify::expanded', self._on_expander_toggled, space_id)
        
        # Container for all children (mix of rooms and nested expanders)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.set_margin_start(12) # Indent children relative to parent
        
        # Children can be spaces or rooms
        children_ids = hierarchy["children"].get(space_id, [])
        
        # To keep it efficient and selection-friendly, we group adjacent rooms 
        # into a single ListBox, but nested spaces get their own Expanders in the Box.
        current_room_list = None
        
        for child_id in children_ids:
            child_room = rooms.get(child_id)
            if not child_room:
                continue
                
            if hierarchy["spaces"].get(child_id):
                # Nested space: another expander
                nested_expander = self._create_space_expander(child_id, child_room, hierarchy, rooms, depth + 1)
                content_box.append(nested_expander)
                current_room_list = None # Break the room list grouping
            else:
                # Regular room: add to a listbox
                if current_room_list is None:
                    current_room_list = Gtk.ListBox()
                    current_room_list.add_css_class("navigation-sidebar")
                    current_room_list.connect('row-activated', self.on_row_activated)
                    self.all_list_boxes.append(current_room_list)
                    content_box.append(current_room_list)
                
                row = self._create_room_row(child_id, child_room)
                current_room_list.append(row)
            
        expander.set_child(content_box)
        return expander

    def _create_orphans_expander(self, orphan_ids, rooms):
        """Create an expander for rooms without a space."""
        expander = Gtk.Expander()
        
        label = Gtk.Label(label="Rooms & DMs")
        label.set_halign(Gtk.Align.START)
        label.set_margin_start(12)
        label.set_margin_top(8)
        label.set_margin_bottom(8)
        expander.set_label_widget(label)
        
        # Restore state
        is_expanded = self.expander_states.get("orphans", True) # Default open for orphans
        expander.set_expanded(is_expanded)
        expander.connect('notify::expanded', self._on_expander_toggled, "orphans")
        
        room_list = Gtk.ListBox()
        room_list.add_css_class("navigation-sidebar")
        room_list.connect('row-activated', self.on_row_activated)
        self.all_list_boxes.append(room_list)
        
        for rid in orphan_ids:
            room = rooms.get(rid)
            if room:
                row = self._create_room_row(rid, room)
                room_list.append(row)
                
        expander.set_child(room_list)
        return expander

    def _create_room_item_widget(self, room_id, room):
        """Create the widget used for room/space display in rows or headers."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(12)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(12)
        
        # Avatar
        avatar_widget = Adw.Avatar.new(32, room.display_name or room_id, True)
        box.append(avatar_widget)
        
        # Name
        name_label = Gtk.Label(label=room.display_name or room_id)
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3)
        box.append(name_label)
        
        # Check if it's a space (by checking room_type attribute in nio.rooms.MatrixRoom)
        if room.room_type == "m.space":
            name_label.add_css_class("space-name")
            # Add a small indicator icon for space
            icon = Gtk.Image.new_from_icon_name("folder-symbolic")
            icon.set_opacity(0.5)
            box.append(icon)
        
        # Load avatar
        if room.room_avatar_url:
            self.app.loop.create_task(
                self._load_room_avatar(avatar_widget, room.room_avatar_url)
            )
            
        return box

    def _create_room_row(self, room_id, room):
        """Create a ListBoxRow for a room."""
        row = Gtk.ListBoxRow()
        row.room_id = room_id
        
        widget = self._create_room_item_widget(room_id, room)
        row.set_child(widget)
        
        # Store for updates
        self.room_rows[room_id] = row
        return row

    async def _load_room_avatar(self, avatar_widget, avatar_url):
        """Load room avatar asynchronously."""
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
                        logger.error(f"Failed to create texture: {e}")
                GLib.idle_add(update_avatar)
        except Exception as e:
            logger.error(f"Error loading avatar: {e}")

    def _on_expander_toggled(self, expander, _pspec, space_id):
        """Save expander state."""
        self.expander_states[space_id] = expander.get_expanded()

    def on_row_activated(self, list_box, row):
        """Handle room row activation and sync selection across ListBoxes."""
        if hasattr(row, 'room_id'):
            # Clear other selections
            for lb in self.all_list_boxes:
                if lb != list_box:
                    lb.unselect_all()
            
            self.selected_room = row.room_id
            self.emit('room-selected', row.room_id)

    def on_join_clicked(self, _button):
        """Show join room dialog (same as before)."""
        dialog = Gtk.Dialog()
        dialog.set_transient_for(self.get_root())
        dialog.set_modal(True)
        dialog.set_title("Join Room")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Join", Gtk.ResponseType.OK)
        
        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_all(12)
        
        entry = Gtk.Entry()
        entry.set_placeholder_text("#room:matrix.org")
        content.append(entry)
        
        dialog.connect('response', self.on_join_dialog_response, entry)
        dialog.present()

    def on_join_dialog_response(self, dialog, response, entry):
        if response == Gtk.ResponseType.OK:
            room_id = entry.get_text().strip()
            if room_id:
                self.app.loop.create_task(self._join_room(room_id))
        dialog.close()

    async def _join_room(self, room_id):
        success = await self.matrix_client.join_room(room_id)
        if success:
            logger.info(f"Joined {room_id}")
            # Hierarchy will refresh on next sync
