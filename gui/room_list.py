"""
Unified, Flicker-Free Room list sidebar view.
"""

import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gdk, GObject, GLib

logger = logging.getLogger(__name__)


class RoomListView(Gtk.Box):
    """Sidebar view showing rooms organized by spaces in a unified flicker-free list."""
    
    __gsignals__ = {
        'room-selected': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }
    
    def __init__(self, application, matrix_client):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        
        self.app = application
        self.matrix_client = matrix_client
        self.avatar_manager = application.avatar_manager
        self.selected_room = None
        
        # PERSISTENT widgets to prevent flicker
        self.room_rows = {} # room_id -> row widget
        self.header_rows = {} # title -> row widget
        self.expander_states = {} # space_id -> expanded (bool)
        
        self.add_css_class("sidebar")
        self._build_ui()
    
    def _build_ui(self):
        # Header
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
        
        # Scrolled Window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # UNIFIED ListBox
        self.main_list = Gtk.ListBox()
        self.main_list.add_css_class("navigation-sidebar")
        self.main_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.main_list.connect('row-activated', self.on_row_activated)
        
        self.scrolled.set_child(self.main_list)
        self.append(self.scrolled)
        
        # Join Button
        join_button = Gtk.Button(label="Join Room")
        join_button.set_margin_top(12)
        join_button.set_margin_bottom(12)
        join_button.set_margin_start(12)
        join_button.set_margin_end(12)
        join_button.connect('clicked', self.on_join_clicked)
        self.append(join_button)

    def refresh_rooms(self, response=None):
        """Refresh the room list hierarchy WITHOUT rebuilding everything (No flicker)."""
        hierarchy = self.matrix_client.get_hierarchy()
        rooms = self.matrix_client.get_rooms()
        
        # 1. Determine the target order of IDs
        target_rows = [] # list of (id, rtype, depth)
        
        for space_id in hierarchy["top_level_spaces"]:
            room = rooms.get(space_id)
            if room:
                self._build_target_order(space_id, room, hierarchy, rooms, 0, target_rows)
        
        if hierarchy["orphans"]:
            target_rows.append(("hdr_orphans", "header", 0))
            for rid in hierarchy["orphans"]:
                target_rows.append((rid, "room", 0))
        
        # 2. Incremental Update
        active_widgets = set()
        
        for index, (row_id, rtype, depth) in enumerate(target_rows):
            # Find or create the row widget
            if rtype == "header":
                row_widget = self._get_header_row(row_id, "Rooms & DMs")
            elif rtype == "space":
                room = rooms.get(row_id)
                row_widget = self._get_space_row(row_id, room, depth)
            else:
                room = rooms.get(row_id)
                row_widget = self._get_room_row(row_id, room, depth)
            
            active_widgets.add(row_widget)
            
            # Check position
            current_at_index = self.main_list.get_row_at_index(index)
            if current_at_index != row_widget:
                # Safely move to the correct index
                parent = row_widget.get_parent()
                if parent == self.main_list:
                    # In GTK4, to reorder we can remove and insert at new index
                    self.main_list.remove(row_widget)
                elif parent:
                    parent.remove(row_widget)
                
                self.main_list.insert(row_widget, index)
        
        # 3. Remove widgets no longer in the list
        child = self.main_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if child not in active_widgets:
                self.main_list.remove(child)
            child = next_child

        # 4. Restore highlight
        if self.selected_room:
            row = self.room_rows.get(self.selected_room)
            if row and row.get_parent() == self.main_list:
                # Use idle_add to ensure selection happens after reordering completes
                GLib.idle_add(lambda: self.main_list.select_row(row))

    def _build_target_order(self, space_id, room, hierarchy, rooms, depth, target_rows):
        target_rows.append((space_id, "space", depth))
        
        if self.expander_states.get(space_id, False):
            children_ids = hierarchy["children"].get(space_id, [])
            for child_id in children_ids:
                child_room = rooms.get(child_id)
                if not child_room: continue
                
                if hierarchy["spaces"].get(child_id):
                    self._build_target_order(child_id, child_room, hierarchy, rooms, depth + 1, target_rows)
                else:
                    target_rows.append((child_id, "room", depth + 1))

    def _get_header_row(self, row_id, title):
        if row_id in self.header_rows:
            return self.header_rows[row_id]
            
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_selectable(False)
        
        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        label.set_margin_top(8)
        label.set_margin_bottom(4)
        label.set_margin_start(4) # Aligned with space arrow position
        label.add_css_class("space-name")
        row.set_child(label)
        
        self.header_rows[row_id] = row
        return row

    def _get_space_row(self, space_id, room, depth):
        if space_id in self.room_rows:
            # Update rotation
            row = self.room_rows[space_id]
            box = row.get_child()
            btn = box.get_first_child()
            is_expanded = self.expander_states.get(space_id, False)
            btn.set_icon_name("pan-down-symbolic" if is_expanded else "pan-end-symbolic")
            return row
            
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4 + (depth * 12))
        box.set_margin_end(8)
        
        is_expanded = self.expander_states.get(space_id, False)
        toggle_btn = Gtk.Button()
        toggle_btn.set_has_frame(False)
        toggle_btn.set_icon_name("pan-down-symbolic" if is_expanded else "pan-end-symbolic")
        toggle_btn.connect("clicked", self.on_expander_clicked, space_id)
        box.append(toggle_btn)
        
        avatar = Adw.Avatar.new(32, room.display_name or space_id, True)
        box.append(avatar)
        if room.room_avatar_url:
            self.app.loop.create_task(self._load_avatar(avatar, room.room_avatar_url))
            
        label = Gtk.Label(label=room.display_name or space_id)
        label.add_css_class("space-name")
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        box.append(label)
        
        row.set_child(box)
        self.room_rows[space_id] = row
        return row

    def _get_room_row(self, room_id, room, depth):
        if room_id in self.room_rows:
            return self.room_rows[room_id]
            
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_spacing(12)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        
        # Room indentation: Orphan rooms (depth 0) align with headers.
        start_margin = 4 if depth == 0 else 32 + (depth * 12)
        box.set_margin_start(start_margin) 
        box.set_margin_end(12)
        
        avatar = Adw.Avatar.new(32, room.display_name or room_id, True)
        box.append(avatar)
        if room.room_avatar_url:
            self.app.loop.create_task(self._load_avatar(avatar, room.room_avatar_url))
            
        label = Gtk.Label(label=room.display_name or room_id)
        label.set_halign(Gtk.Align.START)
        label.set_ellipsize(3)
        label.set_hexpand(True)
        box.append(label)
        
        if hasattr(room, 'encrypted') and room.encrypted:
            lock_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
            lock_icon.set_opacity(0.5)
            box.append(lock_icon)
        
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

    def on_expander_clicked(self, btn, space_id):
        self.expander_states[space_id] = not self.expander_states.get(space_id, False)
        self.refresh_rooms()

    def on_row_activated(self, list_box, row):
        # We need to find the room_id from self.room_rows since it's not stored on the row object directly here
        room_id = None
        for rid, widget in self.room_rows.items():
            if widget == row:
                room_id = rid
                break
        
        if room_id:
            self.selected_room = room_id
            self.emit('room-selected', room_id)

    def on_join_clicked(self, _button):
        dialog = Gtk.Dialog(title="Join Room", transient_for=self.get_root(), modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Join", Gtk.ResponseType.OK)
        entry = Gtk.Entry(placeholder_text="#room:matrix.org")
        content = dialog.get_content_area()
        content.set_margin_top(12); content.set_margin_bottom(12)
        content.set_margin_start(12); content.set_margin_end(12)
        content.append(entry)
        dialog.connect('response', self.on_join_dialog_response, entry)
        dialog.present()

    def on_join_dialog_response(self, dialog, response, entry):
        if response == Gtk.ResponseType.OK:
            room_id = entry.get_text().strip()
            if room_id: self.app.loop.create_task(self.matrix_client.join_room(room_id))
        dialog.close()
