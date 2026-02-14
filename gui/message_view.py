"""
Message timeline view.
"""

import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gdk, GLib, Pango, Gio
from nio import RoomMessageText, RoomMessagesResponse, RoomMessageImage, RoomGetEventError, MegolmEvent
from .image_viewer import ImageViewer

logger = logging.getLogger(__name__)


class MessageView(Gtk.Box):
    """Message timeline and input view."""
    
    def __init__(self, application, matrix_client, avatar_manager):
        """Initialize message view.
        
        Args:
            application: The main application instance
            matrix_client: MatrixClient instance
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        
        self.app = application
        self.matrix_client = matrix_client
        self.avatar_manager = avatar_manager
        self.current_room_id = None
        
        # Reply state
        self._reply_to_event = None
        
        # Scroll state
        self._autoscroll = True
        self.scrolled = Gtk.ScrolledWindow()
        self._scroll_adj = self.scrolled.get_vadjustment()
        self._scroll_adj.connect('value-changed', self.on_scroll_changed)
        self._scroll_adj.connect('changed', self.on_adjustment_changed)
        
        self._build_ui()
        
        self._last_sender = None
        self._last_timestamp = 0
        self._last_room_id = None
        self._shown_event_ids = set()
        self._profile_cache = {} # user_id -> profile_dict
        self.prev_batch = None
        
        # Register message callback
        if self.matrix_client.client:
            self.matrix_client.client.add_event_callback(self.on_room_message, RoomMessageText)
            self.matrix_client.client.add_event_callback(self.on_room_message, RoomMessageImage)
            self.matrix_client.client.add_event_callback(self.on_room_message, MegolmEvent)
    
    def _build_ui(self):
        """Build the message view UI."""
        # Room header
        self.room_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.room_header.set_margin_top(12)
        self.room_header.set_margin_bottom(12)
        self.room_header.set_margin_start(16)
        self.room_header.set_margin_end(16)
        self.room_header.add_css_class("toolbar")
        
        self.room_title = Gtk.Label(label="Select a room")
        self.room_title.set_halign(Gtk.Align.START)
        self.room_title.set_hexpand(True)
        self.room_title.add_css_class("title-2")
        self.room_header.append(self.room_title)
        
        # Leave room button
        self.leave_button = Gtk.Button(label="Leave Room")
        self.leave_button.set_sensitive(False)
        self.leave_button.connect('clicked', self.on_leave_clicked)
        self.room_header.append(self.leave_button)
        
        self.append(self.room_header)
        
        # Overlay for floating indicator
        self.overlay = Gtk.Overlay()
        self.overlay.set_vexpand(True)
        
        # Message list (scrollable)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # ListBox for messages
        self.message_list = Gtk.ListBox()
        self.message_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.message_list.add_css_class("message-list")
        
        # Load More Button (at the top)
        self.load_more_row = Gtk.ListBoxRow()
        self.load_more_row.set_selectable(False)
        self.load_more_button = Gtk.Button(label="Load older messages")
        self.load_more_button.add_css_class("flat")
        self.load_more_button.add_css_class("load-more-button")
        self.load_more_button.connect('clicked', self.on_load_more_clicked)
        self.load_more_row.set_child(self.load_more_button)
        self.message_list.append(self.load_more_row)
        
        self.scrolled.set_child(self.message_list)
        self.overlay.set_child(self.scrolled)
        
        # New Messages Indicator
        self.indicator_bin = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.indicator_bin.set_halign(Gtk.Align.CENTER)
        self.indicator_bin.set_valign(Gtk.Align.END)
        self.indicator_bin.set_margin_bottom(12)
        self.indicator_bin.set_visible(False)
        
        self.indicator_button = Gtk.Button(label="New Messages ↓")
        self.indicator_button.add_css_class("new-messages-indicator")
        self.indicator_button.connect('clicked', self.on_indicator_clicked)
        self.indicator_bin.append(self.indicator_button)
        
        self.overlay.add_overlay(self.indicator_bin)
        self.append(self.overlay)
        
        # Reply Preview area
        self.reply_preview_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.reply_preview_box.set_spacing(8)
        self.reply_preview_box.set_margin_start(16)
        self.reply_preview_box.set_margin_end(16)
        self.reply_preview_box.set_margin_top(4)
        self.reply_preview_box.set_margin_bottom(4)
        self.reply_preview_box.add_css_class("reply-preview")
        self.reply_preview_box.set_visible(False)
        
        self.reply_preview_label = Gtk.Label()
        self.reply_preview_label.set_halign(Gtk.Align.START)
        self.reply_preview_label.set_hexpand(True)
        self.reply_preview_label.set_ellipsize(3) # END
        self.reply_preview_box.append(self.reply_preview_label)
        
        self.cancel_reply_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        self.cancel_reply_button.add_css_class("flat")
        self.cancel_reply_button.connect('clicked', self.on_cancel_reply)
        self.reply_preview_box.append(self.cancel_reply_button)
        
        self.append(self.reply_preview_box)
        
        # Message input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        input_box.set_spacing(8)
        input_box.set_margin_top(8)
        input_box.set_margin_bottom(8)
        input_box.set_margin_start(16)
        input_box.set_margin_end(16)
        
        self.message_entry = Gtk.Entry()
        self.message_entry.set_placeholder_text("Type a message...")
        self.message_entry.set_hexpand(True)
        self.message_entry.connect('activate', self.on_send_message)
        input_box.append(self.message_entry)
        
        send_button = Gtk.Button(label="Send")
        send_button.add_css_class("suggested-action")
        send_button.connect('clicked', self.on_send_message)
        input_box.append(send_button)
        
        self.append(input_box)
    
    def set_room(self, room_id: str):
        """Set the current room.
        
        Args:
            room_id: Room ID to display
        """
        self.current_room_id = room_id
        
        # Update header
        rooms = self.matrix_client.get_rooms()
        if room_id in rooms:
            room = rooms[room_id]
            self.room_title.set_text(room.display_name or room_id)
            self.leave_button.set_sensitive(True)
        
        # Clear state for grouping
        self._last_sender = None
        self._last_timestamp = 0
        self._last_room_id = room_id
        
        # Clear and load messages
        self.load_messages()
    
    def load_messages(self):
        """Load messages for the current room."""
        # Reset scroll state
        self._autoscroll = True
        self.indicator_bin.set_visible(False)
        
        # Clear existing messages
        while True:
            row = self.message_list.get_row_at_index(0)
            if row is None:
                break
            self.message_list.remove(row)
        
        # Reset grouping state
        self._last_sender = None
        self._last_timestamp = 0
        self._shown_event_ids.clear()
        
        if not self.current_room_id:
            return
        
        rooms = self.matrix_client.get_rooms()
        if self.current_room_id not in rooms:
            return
        
        room = rooms[self.current_room_id]
        
        # Load messages from the room's timeline (live)
        if hasattr(room, 'timeline'):
            events = room.timeline
            if hasattr(events, 'events'):
                events = events.events
            
            logger.debug(f"Adding {len(events)} live timeline messages for room {self.current_room_id}")
            for event in events:
                if isinstance(event, RoomMessageText):
                    self.add_message_to_ui(event)
        
        # Fetch history from server
        self.app.loop.create_task(self._fetch_history(self.current_room_id))

    async def _fetch_history(self, room_id: str):
        """Fetch historical messages from server."""
        logger.info(f"Fetching history for room {room_id}")
        response = await self.matrix_client.get_room_messages(room_id)
        
        if isinstance(response, RoomMessagesResponse):
            logger.info(f"Received {len(response.chunk)} historical events")
            self.prev_batch = response.end  # 'end' is usually the token for older messages
            # Events in chunk are usually in reverse chronological order
            # We want to add them at the top, or clear and rebuild
            # For simplicity, we clear and rebuild but properly sorted
            self._rebuild_messages_with_history(response.chunk)

    def _rebuild_messages_with_history(self, history_events):
        """Rebuild message list with historical and live messages."""
        if not self.current_room_id:
            return
            
        # Clear again to ensure proper order
        while True:
            row = self.message_list.get_row_at_index(0)
            if row is None:
                break
            self.message_list.remove(row)
        self._shown_event_ids.clear()
        
        # Restore Load More row
        self.message_list.append(self.load_more_row)
            
        # Get live events
        rooms = self.matrix_client.get_rooms()
        room = rooms[self.current_room_id]
        live_events = []
        if hasattr(room, 'timeline'):
            tl = room.timeline
            live_events = tl.events if hasattr(tl, 'events') else tl
            
        # Combine and sort by timestamp
        all_events = []
        seen_ids = set()
        
        for event in history_events:
            if isinstance(event, (RoomMessageText, RoomMessageImage, MegolmEvent)) and event.event_id not in seen_ids:
                all_events.append(event)
                seen_ids.add(event.event_id)
                
        for event in live_events:
            if isinstance(event, (RoomMessageText, RoomMessageImage, MegolmEvent)) and event.event_id not in seen_ids:
                all_events.append(event)
                seen_ids.add(event.event_id)
        
        # Sort by server timestamp
        all_events.sort(key=lambda e: e.server_timestamp)
        
        for event in all_events:
            try:
                self.add_message_to_ui(event)
            except Exception as e:
                logger.error(f"Failed to add message {getattr(event, 'event_id', 'unknown')} to UI: {e}")
        
        # Initially scroll to bottom
        GLib.idle_add(self.scroll_to_bottom)

    def add_message_to_ui(self, event, prepend=False):
        """Add a message to the UI.
        
        Args:
            event: RoomMessageText or RoomMessageImage event
            prepend: Whether to insert at the top (after Load More row)
        """
        logger.debug(f"Adding event {getattr(event, 'event_id', 'unknown')} of type {type(event).__name__} to UI")
        
        if not hasattr(event, 'event_id') or event.event_id in self._shown_event_ids:
            return
        self._shown_event_ids.add(event.event_id)
        
        try:
            self._add_message_logical(event, prepend=prepend)
        except Exception as e:
            logger.error(f"Critical error adding message {event.event_id} to UI: {e}")

    def _add_message_logical(self, event, prepend=False):
        """Internal method to handle message UI construction without crashing the whole loop."""
        # Check if we are at the bottom before adding
        adj = self._scroll_adj
        was_at_bottom = self._autoscroll
        
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.set_spacing(12)
        hbox.set_margin_start(12)
        hbox.set_margin_end(12)
        hbox.set_margin_top(6)
        hbox.set_margin_bottom(6)
        
        # Avatar Column (Fixed width for alignment)
        avatar_bin = Gtk.Box()
        avatar_bin.set_size_request(32, 32)
        avatar_bin.set_valign(Gtk.Align.START)
        hbox.append(avatar_bin)
        
        # Avatar
        avatar_widget = Adw.Avatar.new(32, "", True)
        avatar_widget.add_css_class("avatar")
        avatar_bin.append(avatar_widget)
        
        # Content box (Vertical: Sender, Body)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_spacing(2)
        vbox.set_hexpand(True)
        hbox.append(vbox)
        
        # Sender info
        sender_id = event.sender
        display_name = sender_id
        avatar_url = None
        
        # Try to get user info from room state
        if self.current_room_id:
            rooms = self.matrix_client.client.rooms
            if self.current_room_id in rooms:
                users = rooms[self.current_room_id].users
                if sender_id in users:
                    user = users[sender_id]
                    display_name = user.display_name or sender_id
                    avatar_url = user.avatar_url
        
        sender_label = Gtk.Label()
        sender_label.set_markup(f"<b>{display_name}</b>")
        sender_label.set_halign(Gtk.Align.START)
        sender_label.set_xalign(0)
        
        # Message body
        body = getattr(event, 'body', "")
        body_label = Gtk.Label(label=body)
        body_label.set_halign(Gtk.Align.START)
        body_label.set_wrap(True)
        body_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body_label.set_xalign(0)
        body_label.set_selectable(True)
        body_label.add_css_class("message-body")
        
        # Decide if we should group this message
        current_ts = event.server_timestamp / 1000.0  # Convert to seconds
        time_diff = current_ts - self._last_timestamp
        
        is_grouped = (
            self._last_sender == sender_id and
            time_diff < 300 and # 5 minutes
            self.current_room_id == self._last_room_id
        )
        
        # We also don't group if it's a reply (replies usually need individual headers/context)
        content = event.source.get('content', {})
        relates_to = content.get('m.relates_to', {})
        in_reply_to = relates_to.get('m.in_reply_to', {})
        is_reply = bool(in_reply_to)
        
        if is_reply:
            is_grouped = False
            
        if is_grouped:
            hbox.add_css_class("grouped")
            # Keep avatar_bin visible for alignment but hide the image
            avatar_widget.set_visible(False)
            # Also reduce margin for grouped
            hbox.set_margin_top(0)
            hbox.set_margin_bottom(0)
        else:
            vbox.append(sender_label)
            self._last_sender = sender_id
            self._last_timestamp = current_ts
            
        # Handle Replies
        if is_reply:
            reply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            reply_box.add_css_class("reply-reference")
            reply_box.set_spacing(6)
            
            reply_icon = Gtk.Image.new_from_icon_name("mail-reply-symbolic")
            reply_icon.set_opacity(0.6)
            reply_box.append(reply_icon)
            
            # Try to resolve the parent event for a better snippet
            relates = event.source['content'].get('m.relates_to', {})
            parent_id = relates.get('m.in_reply_to', {}).get('event_id')
            parent_text = None
            
            if parent_id and self.current_room_id:
                rooms = self.matrix_client.get_rooms()
                if self.current_room_id in rooms:
                    room = rooms[self.current_room_id]
                    # Search timeline for parent
                    timeline = getattr(room, 'timeline', [])
                    for e in timeline:
                        if hasattr(e, 'event_id') and e.event_id == parent_id:
                            if isinstance(e, RoomMessageText):
                                parent_text = e.body
                                break
            
            # Extract plain text from the body (Matrix replies often have a quote header)
            # Find the first line that doesn't start with > for the "real" message
            body_lines = event.body.split('\n')
            clean_body = []
            quote_lines = []
            
            for line in body_lines:
                if line.startswith('>'):
                    # It's a quote, but we only want the text, not the > and not the sender line if it exists
                    # Matrix quotes often look like: > <@user:server> message
                    # Or just: > message
                    quote_content = line.lstrip('>').strip()
                    if quote_content and not (quote_content.startswith('<@') and quote_content.endswith('>')):
                        quote_lines.append(quote_content)
                elif line.strip():
                    clean_body.append(line)
            
            final_body = "\n".join(clean_body)
            # If we didn't find the parent event, use the extracted quote as parent_text
            if parent_text is None and quote_lines:
                parent_text = " ".join(quote_lines)
            
            if parent_text is None:
                parent_text = "Original message"
            
            reply_label = Gtk.Label()
            reply_label.set_halign(Gtk.Align.START)
            reply_label.set_xalign(0)
            reply_label.set_ellipsize(3) # ELLIPSIZE_END
            # Pango markup: span supports alpha and style
            escaped_parent = GLib.markup_escape_text(parent_text[:60])
            reply_label.set_markup(f"<span alpha='60%'>Replying to:</span> <span font_style='italic' alpha='80%'>{escaped_parent}...</span>")
            reply_box.append(reply_label)
            
            vbox.append(reply_box)
            
        # Message Body (Text, Image or Encrypted)
        # Message Body (Text, Image or Encrypted)
        if isinstance(event, MegolmEvent):
            # Try to decrypt if it wasn't already (usually for live events)
            try:
                decrypted = self.matrix_client.client.decrypt_event(event)
                if not isinstance(decrypted, MegolmEvent):
                    event = decrypted
                else:
                    body_label = Gtk.Label(label="Locked message (Waiting for keys...)")
                    body_label.add_css_class("error")
                    vbox.append(body_label)
                    row.set_child(hbox)
                    self.message_list.append(row)
                    return
            except Exception:
                body_label = Gtk.Label(label="Locked message (Waiting for keys...)")
                body_label.add_css_class("error")
                vbox.append(body_label)
                row.set_child(hbox)
                self.message_list.append(row)
                return

        # Content processing after possible decryption
        if isinstance(event, RoomMessageImage):
            # Image message
            image_widget = Gtk.Picture()
            image_widget.set_keep_aspect_ratio(True)
            image_widget.set_can_shrink(True)
            image_widget.add_css_class("message-image")
            image_widget.set_halign(Gtk.Align.START)
            
            # Set a more generous size request to prevent tiny images
            image_widget.set_size_request(300, 200)
            
            # Use hexpand to encourage using available width
            image_widget.set_hexpand(True)
            
            vbox.append(image_widget)
            
            # Load image asynchronously
            self.app.loop.create_task(self._load_message_image(image_widget, event))
            
            # Make clickable
            click_gesture = Gtk.GestureClick()
            click_gesture.connect("pressed", self.on_image_clicked, event)
            image_widget.add_controller(click_gesture)
        elif isinstance(event, (RoomMessageText, MegolmEvent)):
            # Text message (or decrypted MegolmEvent)
            body = event.body if hasattr(event, 'body') else "Decrypted message (Unknown content)"
            body_label = Gtk.Label(label=body)
            body_label.set_halign(Gtk.Align.START)
            body_label.set_xalign(0)
            body_label.set_wrap(True)
            body_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            body_label.set_selectable(True)
            body_label.add_css_class("message-body")
            
            if is_reply:
                # If we parsed quote fallback, update the body label
                if final_body:
                    body_label.set_text(final_body)
            vbox.append(body_label)
        else:
            # Unsupported event type
            body_label = Gtk.Label(label=f"Unsupported message type: {type(event).__name__}")
            body_label.add_css_class("error")
            vbox.append(body_label)
            
        # Right-click context menu gesture
        gesture = Gtk.GestureClick.new()
        gesture.set_button(3) # Right click
        gesture.connect("released", self.on_message_context_menu, event)
        row.add_controller(gesture)

        row.set_child(hbox)
            
        # Store references for quick updates (e.g., during grouping or scrolling)
        row.body_label = body_label
        row.avatar_image = avatar_widget
        row.sender_label = sender_label
        
        if prepend:
            self.message_list.insert(row, 1)
        else:
            self.message_list.append(row)
        
        # Auto-scroll or show indicator
        if not was_at_bottom and not prepend:
            self.indicator_bin.set_visible(True)
        # Note: autoscroll is handled by on_adjustment_changed when was_at_bottom is True
        
        # Load avatar if available, or try to fetch profile
        if not is_grouped:
            self.app.loop.create_task(
                self._resolve_and_load_avatar(sender_id, avatar_widget, avatar_url, sender_label)
            )
    
    def on_room_message(self, room, event):
        """Callback for new room messages."""
        if room.room_id == self.current_room_id:
            if isinstance(event, (RoomMessageText, RoomMessageImage, MegolmEvent)):
                # We are already in the UI thread via async_event_loop tick
                self.add_message_to_ui(event)
    
    async def _resolve_and_load_avatar(self, user_id, avatar_widget, avatar_url, name_label):
        """Resolve avatar URL and load it, updating display name if needed."""
        # Use cache if available
        profile = self._profile_cache.get(user_id)
        
        if not profile and not avatar_url:
            profile = await self.matrix_client.get_user_profile(user_id)
            if profile:
                self._profile_cache[user_id] = profile
        
        display_name = user_id
        if profile:
            avatar_url = profile.get("avatar_url")
            display_name = profile.get("displayname") or user_id
            if profile.get("displayname"):
                GLib.idle_add(name_label.set_markup, f"<b>{profile['displayname']}</b>")
        
        # Update Adw.Avatar initials
        GLib.idle_add(avatar_widget.set_text, display_name)
        
        if avatar_url:
            await self._load_avatar_for_image(avatar_widget, avatar_url)
    
    async def _load_message_image(self, image_widget, event):
        """Asynchronously load and display a message image."""
        try:
            # Max width 400px, max height 300px for more compact view
            path = await self.matrix_client.media_manager.get_media(
                self.matrix_client.homeserver,
                event.url,
                width=400,
                height=300,
                access_token=self.matrix_client.client.access_token
            )
            
            if path:
                gfile = Gio.File.new_for_path(str(path))
                GLib.idle_add(image_widget.set_file, gfile)
        except Exception as e:
            logger.error(f"Failed to load message image {event.url}: {e}")

    async def _load_avatar_for_image(self, avatar_widget, avatar_url):
        """Load avatar asynchronously and update avatar widget."""
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
            logger.error(f"Error loading avatar: {e}")
    
    
    def on_scroll_changed(self, adj):
        """Handle scroll position changes."""
        value = adj.get_value()
        upper = adj.get_upper()
        page_size = adj.get_page_size()
        
        # If we are within 100px of bottom, enable autoscroll
        # Using a slightly larger threshold (100px) to be more forgiving
        at_bottom = (upper - page_size - value) < 100
        if at_bottom:
            self._autoscroll = True
            self.indicator_bin.set_visible(False)
        else:
            self._autoscroll = False

    def on_adjustment_changed(self, adj):
        """Handle content size changes."""
        if self._autoscroll:
            # Use idle_add to ensure the ListBox has finished layout and the 
            # adjustment's upper value is correctly updated for the new content.
            GLib.idle_add(self.scroll_to_bottom)

    def scroll_to_bottom(self):
        """Scroll message list to the bottom."""
        if not self.scrolled:
            return False
            
        adj = self._scroll_adj
        upper = adj.get_upper()
        page_size = adj.get_page_size()
        
        # Scroll to the very end
        adj.set_value(upper - page_size)
        self._autoscroll = True
        return False  # Don't call again from idle_add

    def on_indicator_clicked(self, _button):
        """Handle indicator click to jump to bottom."""
        self.scroll_to_bottom()
        self.indicator_bin.set_visible(False)

    def on_load_more_clicked(self, _button):
        """Handle Load More button click."""
        if self.current_room_id and self.prev_batch:
            self.load_more_button.set_sensitive(False)
            self.load_more_button.set_label("Loading...")
            self.app.loop.create_task(self._load_more_history())

    async def _load_more_history(self):
        """Fetch older messages and prepend them."""
        try:
            response = await self.matrix_client.get_room_messages(
                self.current_room_id, 
                start=self.prev_batch
            )
            if isinstance(response, RoomMessagesResponse):
                self.prev_batch = response.end
                if not response.chunk:
                    GLib.idle_add(self.load_more_button.set_label, "No more messages")
                    return
                
                # Prepend messages
                # For simplicity, we can just rebuild everything or surgically prepend.
                # Surgical prepend is better for performance.
                GLib.idle_add(self._prepend_history_events, response.chunk)
        except Exception as e:
            logger.error(f"Failed to load more history: {e}")
        finally:
            GLib.idle_add(self.load_more_button.set_sensitive, True)
            GLib.idle_add(self.load_more_button.set_label, "Load older messages")

    def _prepend_history_events(self, events):
        """Surgically prepend older events to the UI."""
        # Reverse to get chronological order for prepending
        for event in reversed(events):
            # We need a special add method that inserts after the load_more_row
            self._add_message_logical(event, prepend=True)

    def on_send_message(self, _widget):
        """Handle send message."""
        if not self.current_room_id:
            return
        
        message = self.message_entry.get_text().strip()
        if not message:
            return
        
        # Clear entry
        self.message_entry.set_text("")
        
        # Collect reply info
        reply_to_id = None
        reply_to_body = None
        if self._reply_to_event:
            reply_to_id = self._reply_to_event.event_id
            reply_to_body = getattr(self._reply_to_event, 'body', None)
            self.on_cancel_reply()
        
        # Send message asynchronously
        self.app.loop.create_task(
            self.matrix_client.send_message(
                self.current_room_id, 
                message, 
                reply_to_id=reply_to_id, 
                reply_to_body=reply_to_body
            )
        )
    
    def on_leave_clicked(self, _button):
        """Handle leave room button click."""
        if not self.current_room_id:
            return
        
        self.app.loop.create_task(self._leave_room())
    
    async def _leave_room(self):
        """Leave the current room."""
        if self.current_room_id:
            logger.info(f"Leaving room: {self.current_room_id}")
            await self.matrix_client.leave_room(self.current_room_id)
            
            # Clear view
            GLib.idle_add(self._clear_room_view)
    
    def _clear_room_view(self):
        """Clear the room view after leaving."""
        self.current_room_id = None
        self.room_title.set_text("Select a room")
        self.leave_button.set_sensitive(False)
        
        # Clear messages
        while True:
            row = self.message_list.get_row_at_index(0)
            if row is None:
                break
            self.message_list.remove(row)

    def on_image_clicked(self, gesture, n_press, x, y, event):
        """Handle click on message image."""
        self.app.loop.create_task(self._open_full_image(event))

    def on_message_context_menu(self, gesture, n_press, x, y, event):
        """Show context menu for a message."""
        menu = Gio.Menu.new()
        
        # Add actions
        menu.append("Copy Username", "copy_username")
        menu.append("Copy Message", "copy_message")
        menu.append("Reply", "reply")
        
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(gesture.get_widget())
        popover.set_pointing_to(Gdk.Rectangle()) # Points to click location if possible, or center
        
        # Define actions locally for the popover
        action_group = Gio.SimpleActionGroup.new()
        
        # Copy Username action
        copy_user_action = Gio.SimpleAction.new("copy_username", None)
        copy_user_action.connect("activate", lambda *_: self.copy_to_clipboard(event.sender))
        action_group.add_action(copy_user_action)
        
        # Copy Message action
        body = getattr(event, 'body', "")
        copy_msg_action = Gio.SimpleAction.new("copy_message", None)
        copy_msg_action.connect("activate", lambda *_: self.copy_to_clipboard(body))
        action_group.add_action(copy_msg_action)
        
        # Reply action
        reply_action = Gio.SimpleAction.new("reply", None)
        reply_action.connect("activate", lambda *_: self.on_reply_clicked(None, event))
        action_group.add_action(reply_action)
        
        gesture.get_widget().insert_action_group("msg", action_group)
        popover.set_has_arrow(False)
        popover.set_autohide(True)
        
        # Connect actions to the menu items
        # In GTK4 PopoverMenu from model, actions are expected at prefix.name
        # We need to update the menu items to use the prefix
        menu.remove_all()
        menu.append("Copy Username", "msg.copy_username")
        menu.append("Copy Message", "msg.copy_message")
        menu.append("Reply", "msg.reply")
        
        popover.popup()

    def copy_to_clipboard(self, text):
        """Copy text to system clipboard."""
        if not text:
            return
        display = Gdk.Display.get_default()
        clipboard = display.get_clipboard()
        clipboard.set(text)
        logger.debug(f"Copied to clipboard: {text[:20]}...")

    def on_reply_clicked(self, _button, event):
        """Start a reply to the given event."""
        self._reply_to_event = event
        sender = event.sender
        # Try to get display name
        rooms = self.matrix_client.get_rooms()
        if self.current_room_id in rooms:
            user = rooms[self.current_room_id].users.get(sender)
            if user:
                sender = user.display_name or sender
        
        body = getattr(event, 'body', "Image")
        if isinstance(event, RoomMessageImage):
            body = "Image"
            
        self.reply_preview_label.set_markup(f"<span alpha='70%'>Replying to <b>{GLib.markup_escape_text(sender)}</b>:</span> {GLib.markup_escape_text(body[:50])}")
        self.reply_preview_box.set_visible(True)
        self.message_entry.grab_focus()

    def on_cancel_reply(self, _button=None):
        """Cancel the current reply."""
        self._reply_to_event = None
        self.reply_preview_box.set_visible(False)

    async def _open_full_image(self, event):
        """Fetch and show full resolution image."""
        try:
            # Download or get full res from cache (no width/height)
            path = await self.matrix_client.media_manager.get_media(
                self.matrix_client.homeserver,
                event.url,
                access_token=self.matrix_client.client.access_token
            )
            
            if path:
                viewer = ImageViewer(self.app.main_window, path, title=event.body)
                viewer.present()
        except Exception as e:
            logger.error(f"Failed to open full image: {e}")
