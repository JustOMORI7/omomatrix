"""
Room list sidebar view with space support and flicker-free updates.
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
        self.room_rows = {} # room_id -> row widget
        self.expanders = {} # space_id -> expander widget
        self.expander_states = {} # space_id -> expanded (bool)
        self.orphans_expander = None
        
        self.add_css_class("sidebar")
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the room list UI."""
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header_box.set_spacing(6)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(12)
        header_box.set_margin_start(12)
        header_box.set_margin_end(12)
        
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search rooms...")
        header_box.append(self.search_entry)
        
        self.append(header_box)
        
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.scrolled.set_child(self.main_container)
        self.append(self.scrolled)
        
        join_button = Gtk.Button(label="Join Room")
        join_button.set_margin_top(12)
        join_button.set_margin_bottom(12)
        join_button.set_margin_start(12)
        join_button.set_margin_end(12)
        join_button.connect('clicked', self.on_join_clicked)
        self.append(join_button)

    def refresh_rooms(self, response=None):
        """Refresh the room list hierarchy incrementally."""
        hierarchy = self.matrix_client.get_hierarchy()
        rooms = self.matrix_client.get_rooms()
        
        current_space_ids = set(hierarchy["top_level_spaces"])
        existing_space_ids = set(self.expanders.keys())
        
        # Remove old spaces
        for sid in existing_space_ids - current_space_ids:
            expander = self.expanders.pop(sid)
            self._safe_remove(self.main_container, expander)
            
        # Clear the sync list
        self.all_list_boxes = []

        # Update or create spaces
        for space_id in hierarchy["top_level_spaces"]:
            room = rooms.get(space_id)
            if not room: continue
            
            if space_id not in self.expanders:
                expander = self._create_space_expander(space_id, room, hierarchy, rooms)
                self.expanders[space_id] = expander
                self.main_container.append(expander)
            else:
                self._update_space_expander(space_id, room, hierarchy, rooms)
        
        # Orphans
        if hierarchy["orphans"]:
            if not self.orphans_expander:
                self.orphans_expander = self._create_orphans_expander(hierarchy["orphans"], rooms)
                self.main_container.append(self.orphans_expander)
            else:
                self._update_orphans_expander(hierarchy["orphans"], rooms)
        elif self.orphans_expander:
            self._safe_remove(self.main_container, self.orphans_expander)
            self.orphans_expander = None

    def _safe_remove(self, container, widget):
        """Safely remove a widget from a container."""
        if widget and widget.get_parent() == container:
            container.remove(widget)

    def _create_space_expander(self, space_id, room, hierarchy, rooms, depth=0):
        expander = Gtk.Expander()
        expander.add_css_class("room-expander")
        expander.set_margin_start(8 if depth > 0 else 0)
        
        header_box, arrow_icon = self._create_header_widget(room.display_name or space_id, room, is_expander=True)
        header_box.set_hexpand(True)
        expander.set_label_widget(header_box)
        
        is_expanded = self.expander_states.get(space_id, False)
        expander.set_expanded(is_expanded)
        
        if is_expanded:
            arrow_icon.set_from_icon_name("pan-down-symbolic")
        else:
            arrow_icon.set_from_icon_name("pan-end-symbolic")

        expander.connect('notify::expanded', self._on_expander_toggled, space_id, arrow_icon)
        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.set_margin_start(12)
        expander.set_child(content_box)
        
        self._update_expander_content(expander, space_id, hierarchy, rooms, depth)
        return expander

    def _update_space_expander(self, space_id, room, hierarchy, rooms):
        expander = self.expanders[space_id]
        self._update_expander_content(expander, space_id, hierarchy, rooms, 0)

    def _update_expander_content(self, expander, space_id, hierarchy, rooms, depth):
        content_box = expander.get_child()
        children_ids = hierarchy["children"].get(space_id, [])
        
        # Clear structure
        while (child := content_box.get_first_child()):
            content_box.remove(child)
            
        current_room_list = Gtk.ListBox()
        current_room_list.add_css_class("navigation-sidebar")
        current_room_list.connect('row-activated', self.on_row_activated)
        self.all_list_boxes.append(current_room_list)
        
        has_rooms = False
        for child_id in children_ids:
            child_room = rooms.get(child_id)
            if not child_room: continue
            
            if hierarchy["spaces"].get(child_id):
                nested = self._create_space_expander(child_id, child_room, hierarchy, rooms, depth + 1)
                content_box.append(nested)
            else:
                row = self._get_or_create_room_row(child_id, child_room)
                current_room_list.append(row)
                has_rooms = True
        
        if has_rooms:
            content_box.prepend(current_room_list)

    def _create_orphans_expander(self, orphan_ids, rooms):
        expander = Gtk.Expander()
        expander.add_css_class("room-expander")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(12)
        box.set_hexpand(True)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(12)
        
        label = Gtk.Label(label="Rooms & DMs")
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.add_css_class("space-name")
        box.append(label)
        
        arrow_icon = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        arrow_icon.set_opacity(0.7)
        box.append(arrow_icon)
        
        expander.set_label_widget(box)
        
        is_expanded = self.expander_states.get("orphans", True)
        expander.set_expanded(is_expanded)
        if is_expanded:
            arrow_icon.set_from_icon_name("pan-down-symbolic")
            
        expander.connect('notify::expanded', self._on_expander_toggled, "orphans", arrow_icon)
        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.set_margin_start(12)
        expander.set_child(content_box)
        
        self._update_orphans_content(expander, orphan_ids, rooms)
        return expander

    def _update_orphans_expander(self, orphan_ids, rooms):
        self._update_orphans_content(self.orphans_expander, orphan_ids, rooms)

    def _update_orphans_content(self, expander, orphan_ids, rooms):
        content_box = expander.get_child()
        while (child := content_box.get_first_child()):
            content_box.remove(child)
            
        room_list = Gtk.ListBox()
        room_list.add_css_class("navigation-sidebar")
        room_list.connect('row-activated', self.on_row_activated)
        self.all_list_boxes.append(room_list)
        content_box.append(room_list)
        
        for rid in orphan_ids:
            room = rooms.get(rid)
            if room:
                row = self._get_or_create_room_row(rid, room)
                room_list.append(row)

    def _create_header_widget(self, title, room=None, is_expander=False):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(12)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(12)
        
        if room:
            avatar = Adw.Avatar.new(32, title, True)
            box.append(avatar)
            if room.room_avatar_url:
                self.app.loop.create_task(self._load_avatar(avatar, room.room_avatar_url))
            
        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.add_css_class("space-name")
        box.append(label)
        
        arrow_icon = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        arrow_icon.set_opacity(0.7)
        box.append(arrow_icon)
        
        if is_expander:
            return box, arrow_icon
        return box

    def _get_or_create_room_row(self, room_id, room):
        row = self.room_rows.get(room_id)
        if row:
            # IMPORTANT: Remove from previous parent before reuse to avoid "Tried to remove non-child"
            parent = row.get_parent()
            if parent:
                parent.remove(row)
            return row
            
        row = Gtk.ListBoxRow()
        row.room_id = room_id
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(12)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(12)
        
        avatar = Adw.Avatar.new(32, room.display_name or room_id, True)
        box.append(avatar)
        
        label = Gtk.Label(label=room.display_name or room_id)
        label.set_halign(Gtk.Align.START)
        label.set_ellipsize(3)
        box.append(label)
        
        if room.room_avatar_url:
            self.app.loop.create_task(self._load_avatar(avatar, room.room_avatar_url))
            
        row.set_child(box)
        self.room_rows[room_id] = row
        return row

    async def _load_avatar(self, avatar_widget, avatar_url):
        try:
            path = await self.avatar_manager.get_avatar(
                self.matrix_client.homeserver, avatar_url, size=32,
                access_token=self.matrix_client.client.access_token
            )
            if path:
                def update():
                    try:
                        texture = Gdk.Texture.new_from_filename(str(path))
                        avatar_widget.set_custom_image(texture)
                    except: pass
                GLib.idle_add(update)
        except: pass

    def _on_expander_toggled(self, expander, _pspec, space_id, arrow_icon):
        expanded = expander.get_expanded()
        self.expander_states[space_id] = expanded
        if arrow_icon:
            if expanded:
                arrow_icon.set_from_icon_name("pan-down-symbolic")
            else:
                arrow_icon.set_from_icon_name("pan-end-symbolic")

    def on_row_activated(self, list_box, row):
        if hasattr(row, 'room_id'):
            for lb in self.all_list_boxes:
                if lb != list_box: lb.unselect_all()
            self.selected_room = row.room_id
            self.emit('room-selected', row.room_id)

    def on_join_clicked(self, _button):
        dialog = Gtk.Dialog(title="Join Room", transient_for=self.get_root(), modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Join", Gtk.ResponseType.OK)
        entry = Gtk.Entry(placeholder_text="#room:matrix.org")
        
        content = dialog.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.append(entry)
        
        dialog.connect('response', self.on_join_dialog_response, entry)
        dialog.present()

    def on_join_dialog_response(self, dialog, response, entry):
        if response == Gtk.ResponseType.OK:
            room_id = entry.get_text().strip()
            if room_id: self.app.loop.create_task(self.matrix_client.join_room(room_id))
        dialog.close()
