from utils.qt import QtWidgets, QtCore, QtGui, Signal, Slot
from models.messages import MessageModel
from models.rooms_model import RoomListModel
from models.spaces_model import SpacesModel
from core.client import MatrixWorker

import asyncio
import sys
import os

class MainWindow(QtWidgets.QMainWindow):
    """
    Main Application Window.
    Follows the classic 3-column Discord layout using QSplitter.
    """
    
    start_login = Signal(str, str, str) # homeserver, user, pass

    def __init__(self, worker: MatrixWorker):
        super().__init__()
        self.worker = worker
        self.setWindowTitle("OMOMatrix")
        self.resize(1000, 700)
        self.current_room_id = None
        self.current_space_id = None  # Track selected space
        
        # Initialize image cache
        from utils.image_cache import ImageCache
        self.image_cache = ImageCache()
        
        # Central Widget & Layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Disable main UI until login
        central_widget.setEnabled(False)
        
        # 3-Column Splitter
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # 1. Spaces Column (Sidebar)
        spaces_container = QtWidgets.QWidget()
        spaces_layout = QtWidgets.QVBoxLayout(spaces_container)
        
        self.spaces_list = QtWidgets.QListView()
        self.spaces_list.setMinimumWidth(100)
        
        self.spaces_model = SpacesModel(self)
        self.spaces_list.setModel(self.spaces_model)
        
        # Bottom Buttons for Spaces Column
        btn_layout = QtWidgets.QVBoxLayout()
        
        self.leave_btn = QtWidgets.QPushButton("Leave (-)")
        self.leave_btn.clicked.connect(self.on_leave_clicked)
        self.leave_btn.setToolTip("Leave selected room or space")
        
        self.join_btn = QtWidgets.QPushButton("Join (+)")
        self.join_btn.clicked.connect(self.on_join_clicked)
        
        btn_layout.addWidget(self.leave_btn)
        btn_layout.addWidget(self.join_btn)
        
        spaces_layout.addWidget(self.spaces_list)
        spaces_layout.addLayout(btn_layout)
        
        self.splitter.addWidget(spaces_container)
        
        # 2. Rooms Column (Width: Medium)
        rooms_container = QtWidgets.QWidget()
        rooms_layout = QtWidgets.QVBoxLayout(rooms_container)
        
        self.rooms_list = QtWidgets.QListView()
        self.rooms_list.setMinimumWidth(150)
        self.room_model = RoomListModel(self)
        self.rooms_list.setModel(self.room_model)
        self.rooms_list.clicked.connect(self.on_room_clicked)
        
        rooms_layout.addWidget(self.rooms_list)
        
        self.splitter.addWidget(rooms_container)
        
        # 3. Chat Column (Width: Large)
        chat_widget = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(chat_widget)
        
        # Room Header
        self.room_header = QtWidgets.QLabel("Select a room")
        self.room_header.setStyleSheet("font-weight: bold; padding: 5px;")
        chat_layout.addWidget(self.room_header)
        
        # Message View
        self.message_view = QtWidgets.QListView()
        self.message_view.setWordWrap(True)
        self.message_model = MessageModel(self.worker, self)
        self.message_view.setModel(self.message_model)
        
        # Enable context menu (right-click)
        self.message_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.message_view.customContextMenuRequested.connect(self.on_message_context_menu)
        
        # Enable double-click to open images
        self.message_view.doubleClicked.connect(self.on_message_double_click)
        
        # Enable single-click to expand/collapse reply quotes
        self.message_view.clicked.connect(self.message_model.toggle_quote_expansion)
        
        
        # Create custom delegate for HTML rendering with image support
        import asyncio
        
        class HtmlDelegate(QtWidgets.QStyledItemDelegate):
            def __init__(self, parent):
                super().__init__(parent)
            
            def paint(self, painter, option, index):
                options = QtWidgets.QStyleOptionViewItem(option)
                self.initStyleOption(options, index)
                
                painter.save()
                
                # Create QTextDocument to render HTML
                doc = QtGui.QTextDocument()
                doc.setDocumentMargin(6)  # Slightly more padding for comfort
                doc.setDefaultFont(option.font)
                doc.setHtml(options.text)
                
                # Use current wrap width
                width = options.rect.width()
                doc.setTextWidth(width)
                
                # Clear text from options to prevent default rendering
                options.text = ""
                
                # Draw background and focus
                QtWidgets.QApplication.style().drawControl(
                    QtWidgets.QStyle.CE_ItemViewItem, options, painter
                )
                
                # Draw HTML text
                painter.translate(options.rect.left(), options.rect.top())
                clip = QtCore.QRectF(0, 0, options.rect.width(), options.rect.height())
                doc.drawContents(painter, clip)
                
                painter.restore()
            
            def sizeHint(self, option, index):
                options = QtWidgets.QStyleOptionViewItem(option)
                self.initStyleOption(options, index)
                
                doc = QtGui.QTextDocument()
                doc.setDocumentMargin(6)  # Must match paint()
                doc.setDefaultFont(option.font) # CRITICAL: Must use same font for measurement
                doc.setHtml(options.text)
                
                # Get the view's width (minus scrollbar if possible)
                view = self.parent()
                if view:
                    # Subtract some width for the scrollbar to prevent horizontal bumping
                    width = view.viewport().width()
                else:
                    width = option.rect.width() if option.rect.width() > 0 else 500
                
                doc.setTextWidth(width)
                
                height = int(doc.size().height())
                return QtCore.QSize(width, height)
        
        self.message_view.setItemDelegate(HtmlDelegate(self.message_view))
        
        # Allow variable heights for multi-line messages
        self.message_view.setUniformItemSizes(False)
        self.message_view.setResizeMode(QtWidgets.QListView.Adjust)
        chat_layout.addWidget(self.message_view)
        
        # Input Area
        input_layout = QtWidgets.QHBoxLayout()
        self.msg_input = QtWidgets.QLineEdit()
        self.msg_input.setPlaceholderText("Type a message...")
        self.msg_input.returnPressed.connect(self.on_send_message) # Enter key sends
        
        send_btn = QtWidgets.QPushButton("Send")
        send_btn.clicked.connect(self.on_send_message)
        
        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(send_btn)
        
        chat_layout.addLayout(input_layout)
        
        self.splitter.addWidget(chat_widget)
        
        # Set initial stretch factors (index, stretch)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 1)

        # Connect Worker Signals 
        self.worker.login_success.connect(self.on_login_success)
        self.worker.login_failed.connect(self.on_login_failed)
        self.worker.sync_event.connect(self.on_sync_event)
        self.worker.room_list_updated.connect(self.on_room_list_updated)
        self.worker.space_list_updated.connect(self.on_space_list_updated)
        self.worker.history_batch_loaded.connect(self.on_history_loaded)
        self.worker.space_hierarchy_updated.connect(self.on_space_hierarchy_updated)
        self.worker.join_result.connect(self.on_join_result)
        self.worker.room_removed.connect(self.room_model.remove_room)
        self.worker.room_removed.connect(self.spaces_model.remove_space)
        
        # Connect Space and Room clicks
        self.spaces_list.clicked.connect(self.on_space_clicked)
        
        # Show Login Dialog immediately for skeleton
        QtCore.QTimer.singleShot(100, self.show_login_dialog)

    def show_login_dialog(self):
        # Very basic dialog for skeleton
        d = QtWidgets.QDialog(self)
        d.setWindowTitle("Login")
        l = QtWidgets.QVBoxLayout(d)
        
        hs = QtWidgets.QLineEdit("https://matrix.org")
        hs.setPlaceholderText("Homeserver URL")
        
        u = QtWidgets.QLineEdit()
        u.setPlaceholderText("Username")
        
        p = QtWidgets.QLineEdit()
        p.setEchoMode(QtWidgets.QLineEdit.Password)
        p.setPlaceholderText("Password")
        
        btn = QtWidgets.QPushButton("Login")
        l.addWidget(hs)
        l.addWidget(u)
        l.addWidget(p)
        l.addWidget(btn)
        
        def do_login():
            if not hs.text() or not u.text() or not p.text():
                QtWidgets.QMessageBox.warning(d, "Error", "All fields are required!")
                return
            asyncio.create_task(self.worker.login(hs.text(), u.text(), p.text()))
            btn.setEnabled(False)
            btn.setText("Logging in...")
            
        btn.clicked.connect(do_login)
        
        # Store reference so on_login_success can close it
        self._login_dialog = d
        
        # Allow closing the dialog normally (which will return from exec_ with Rejected)
        # If the user rejects the dialog (closes it), we should close the entire application
        if d.exec_() != QtWidgets.QDialog.Accepted:
            print("DEBUG: Login rejected/closed. Exiting application.")
            QtWidgets.QApplication.quit()
            sys.exit(0)

    def _scroll_to_bottom(self):
        """Force scroll to bottom immediately."""
        vbar = self.message_view.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    @Slot(int, int)
    def _on_scroll_range_changed(self, min_val, max_val):
        """Triggered when scrollbar range changes (e.g. messages loaded)."""
        self._scroll_to_bottom()
        # Disconnect to avoid jumping to bottom if user tries to scroll up later
        try:
            self.message_view.verticalScrollBar().rangeChanged.disconnect(self._on_scroll_range_changed)
        except TypeError:
            pass # Already disconnected
    
    @Slot(QtCore.QModelIndex)
    def on_room_clicked(self, index):
        room_id = self.room_model.data(index, RoomListModel.RoomIdRole)
        display_name = self.room_model.data(index, QtCore.Qt.DisplayRole)
        
        print(f"DEBUG: GUI on_room_clicked: {display_name} ({room_id})")
        
        self.current_room_id = room_id
        self.room_header.setText(display_name)
        
        # Filter messages for this room
        self.message_model.set_current_room(room_id)
        
        # Trigger Backfill ONLY if we don't have enough messages cached
        # This prevents the lag reported when switching rooms back and forth
        msg_count = self.message_model.rowCount()
        if msg_count < 20:
            print(f"DEBUG: GUI Triggering Backfill for {room_id} (Count: {msg_count})")
            asyncio.create_task(self.worker.load_room_history(room_id))
        else:
            print(f"DEBUG: Skipping Backfill for {room_id}, already has {msg_count} messages.")
        
        # Snap to bottom as soon as messages arrive and layout is calculated
        vbar = self.message_view.verticalScrollBar()
        # Ensure we connect only once
        try: vbar.rangeChanged.disconnect(self._on_scroll_range_changed)
        except TypeError: pass
        vbar.rangeChanged.connect(self._on_scroll_range_changed)
        
        # Fallback timer
        QtCore.QTimer.singleShot(500, self._scroll_to_bottom)

    @Slot()
    def on_send_message(self):
        text = self.msg_input.text().strip()
        if not text:
            return
        
        if not self.current_room_id:
            QtWidgets.QMessageBox.warning(self, "Error", "Select a room first!")
            return

        # Send via worker
        asyncio.create_task(self.worker.send_message(self.current_room_id, text))
        self.msg_input.clear()

    @Slot(str, str)
    def on_login_success(self, user_id, device_id):
        print(f"DEBUG: GUI on_login_success: {user_id}")
        self.statusBar().showMessage(f"Logged in as {user_id}")
        # Enable UI and close dialog
        self.centralWidget().setEnabled(True)
        if hasattr(self, '_login_dialog'):
            self._login_dialog.accept()

    @Slot(str)
    def on_login_failed(self, error):
        print(f"DEBUG: GUI on_login_failed: {error}")
        QtWidgets.QMessageBox.critical(self, "Login Failed", error)
        # The dialog is still open because we didn't call accept()
        # We should reset the login button in the dialog though
        if hasattr(self, '_login_dialog'):
            # Find the button to re-enable it
            for child in self._login_dialog.findChildren(QtWidgets.QPushButton):
                child.setEnabled(True)
                child.setText("Login")

    @Slot(object)
    def on_sync_event(self, event):
        """
        Handle incoming sync events (messages, etc.)
        """
        # Always add to model so it's cached/available even if not viewing the room
        self.message_model.add_event(event)
        
        # Determine if we should scroll
        room_id = getattr(event, 'room_id', None)
        if room_id == self.current_room_id:
            # Auto-scroll to bottom to show new messages (including images)
            self.message_view.scrollToBottom()
        
    @Slot(str, str)
    def on_room_list_updated(self, room_id, display_name):
        self.room_model.add_or_update_room(room_id, display_name)
        
        # If we are currently looking at "Rooms & DMs", refresh the filter
        # so the newly added room appears immediately.
        if self.current_space_id == "v.spaceless":
            # Small delay to ensure model state is settled if multiple signals arrive
            QtCore.QTimer.singleShot(100, self.refresh_spaceless_filter)

    def refresh_spaceless_filter(self):
        """Re-apply logic for v.spaceless filter."""
        if self.current_space_id != "v.spaceless":
            return
            
        all_known_rooms = list(self.room_model._rooms.keys())
        spaceless_rooms = [rid for rid in all_known_rooms if not self.worker.room_spaces.get(rid)]
        print(f"DEBUG: Refreshing v.spaceless filter. Found {len(spaceless_rooms)} rooms.")
        self.room_model.filter_by_space(spaceless_rooms)

    @Slot(str, str)
    def on_space_list_updated(self, space_id, display_name):
        self.spaces_model.add_or_update_space(space_id, display_name)

    @Slot()
    def on_join_clicked(self):
        """Prompt user for room/space alias or ID to join."""
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Join Room or Space", 
            "Enter Alias or Room ID (e.g. #matrix:matrix.org):"
        )
        if ok and text.strip():
            # Trigger join via worker
            asyncio.create_task(self.worker.join_room(text.strip()))

    @Slot(bool, str)
    def on_join_result(self, success, message):
        """Handle result of join attempt."""
        if success:
            QtWidgets.QMessageBox.information(self, "Join Successful", f"Joined room/space: {message}")
            # The sync loop will automatically add it to the list shortly
        else:
            QtWidgets.QMessageBox.warning(self, "Join Failed", f"Could not join: {message}")

    @Slot()
    def on_leave_clicked(self):
        """Leave the currently selected room or space."""
        # Prioritize the active room if one is selected
        target_id = self.current_room_id or self.current_space_id
        
        if not target_id or target_id == "v.spaceless":
            QtWidgets.QMessageBox.information(self, "Leave", "Please select a room or space to leave.")
            return
            
        confirm = QtWidgets.QMessageBox.question(
            self, "Confirm Leave", 
            f"Are you sure you want to leave?\nID: {target_id}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if confirm == QtWidgets.QMessageBox.Yes:
            asyncio.create_task(self.worker.leave_room(target_id))
            # Clear UI if it was the current room
            if target_id == self.current_room_id:
                self.current_room_id = None
                self.room_header.setText("Select a room")
                self.message_model.clear()

    @Slot(str, list)
    def on_history_loaded(self, room_id, events):
        print(f"DEBUG: GUI on_history_loaded for {room_id} with {len(events)} events")
        if room_id == self.current_room_id:
            # Check if model was empty before prepending
            was_empty = (self.message_model.rowCount() == 0)
            
            # Prepend history events to model
            self.message_model.prepend_batch(events)
            
            # If this was the first load for the room, scroll to newest (bottom)
            if was_empty:
                print("DEBUG: First history load, snapping to bottom")
                self._scroll_to_bottom()
                # Extra insurance: keep snap-to-bottom active for one more range change
                # (since layout might happen in multiple passes)
                vbar = self.message_view.verticalScrollBar()
                try: vbar.rangeChanged.connect(self._on_scroll_range_changed)
                except TypeError: pass 
    
    @Slot(QtCore.QPoint)
    def on_message_context_menu(self, pos):
        """Show context menu for message (right-click)."""
        # Get the index at the clicked position
        index = self.message_view.indexAt(pos)
        if not index.isValid():
            return
        
        # Get message data
        from models.messages import MessageModel
        sender = index.data(MessageModel.SenderRole)
        display_text = index.data(QtCore.Qt.DisplayRole)
        
        # Extract message text (remove HTML tags and sender prefix)
        import re
        # Remove HTML tags
        message_text = re.sub('<[^<]+?>', '', display_text)
        # Remove "sender: " prefix
        if ': ' in message_text:
            message_text = message_text.split(': ', 1)[1]
        
        # Create context menu
        menu = QtWidgets.QMenu(self)
        
        copy_username_action = menu.addAction(f"Copy Username ({sender})")
        copy_message_action = menu.addAction("Copy Message")
        
        # Show menu and get selected action
        action = menu.exec_(self.message_view.viewport().mapToGlobal(pos))
        
        if action == copy_username_action:
            # Copy username to clipboard
            QtWidgets.QApplication.clipboard().setText(sender)
        if action == copy_message_action:
            # Copy message text to clipboard
            QtWidgets.QApplication.clipboard().setText(message_text)

    def _open_file_natively(self, path):
        """High-reliability cross-platform file opening."""
        if not path:
            print("ERROR: _open_file_natively called with empty path")
            return
            
        path_str = str(path)
        if not os.path.exists(path_str):
            print(f"ERROR: File does not exist for opening: {path_str}")
            return
            
        abs_path = os.path.abspath(path_str)
        print(f"DEBUG: Opening file natively: {abs_path}")
        
        if sys.platform == 'win32':
            try:
                # os.startfile is the most reliable way on Windows
                os.startfile(abs_path)
                print("DEBUG: os.startfile initiated.")
                return
            except Exception as e:
                print(f"DEBUG: os.startfile failed ({e}), trying QDesktopServices...")
        
        # Fallback for Windows or primary for Linux/macOS
        url = QtCore.QUrl.fromLocalFile(abs_path)
        success = QtGui.QDesktopServices.openUrl(url)
        if success:
            print(f"DEBUG: QDesktopServices opened URL: {url.toString()}")
        else:
            print(f"ERROR: QDesktopServices failed to open URL: {url.toString()}")

    @Slot(QtCore.QModelIndex)
    def on_message_double_click(self, index):
        """Handle double-click on message - prioritize image or jump to reply."""
        from models.messages import MessageModel
        
        # 1. Check if this is an image message first (Highest priority)
        mxc_url = index.data(MessageModel.ImageUrlRole)
        
        if mxc_url and str(mxc_url).startswith("mxc://"):
            if self.image_cache.is_cached(mxc_url):
                # Open cached image
                local_path = self.image_cache.get_cache_path(mxc_url)
                if local_path and local_path.exists():
                    self._open_file_natively(local_path)
                else:
                    asyncio.create_task(self._download_and_open_image(mxc_url))
            else:
                asyncio.create_task(self._download_and_open_image(mxc_url))
            return # Don't jump if we opened an image

        # 2. Check if it's a reply and we should jump (Second priority)
        parent_id = index.data(MessageModel.ReplyParentRole)
        if parent_id:
            row = self.message_model.get_row_by_event_id(parent_id)
            if row != -1:
                print(f"DEBUG: Jumping to reply parent at row {row}")
                target_index = self.message_model.index(row, 0)
                self.message_view.scrollTo(target_index, QtWidgets.QAbstractItemView.PositionAtCenter)
                self.message_view.setCurrentIndex(target_index)
                return
        else:
             print("DEBUG: Not an image message or no mxc_url")
    
    async def _download_and_open_image(self, mxc_url):
        """Download image and open it."""
        try:
            # Force original quality
            print(f"DEBUG: Starting download for {mxc_url}...")
            data = await self.worker.download_image(mxc_url)
            if data:
                local_path = self.image_cache.save_image(mxc_url, data)
                print(f"DEBUG: Image saved to {local_path}, opening...")
                self._open_file_natively(local_path)
            else:
                print(f"ERROR: Download returned no data for {mxc_url}")
        except Exception as e:
            print(f"DEBUG: Failed to download/open image: {e}")
    
    @Slot(QtCore.QModelIndex)
    def on_space_clicked(self, index):
        """Handle Space selection - filter rooms to show only children of this space."""
        space_id = self.spaces_model.data(index, SpacesModel.SpaceIdRole)
        display_name = self.spaces_model.data(index, QtCore.Qt.DisplayRole)
        
        print(f"DEBUG: GUI on_space_clicked: {display_name} ({space_id})")
        
        self.current_space_id = space_id
        
        if space_id == "v.spaceless":
            # Show all rooms that don't belong to any space (DMs etc)
            all_known_rooms = list(self.room_model._rooms.keys())
            spaceless_rooms = [rid for rid in all_known_rooms if not self.worker.room_spaces.get(rid)]
            print(f"DEBUG: v.spaceless found {len(spaceless_rooms)} rooms without parents out of {len(all_known_rooms)} total.")
            self.room_model.filter_by_space(spaceless_rooms)
            return

        # Get children of this space from worker
        children = self.worker.space_children.get(space_id, [])
        print(f"DEBUG: Space {space_id} has {len(children)} cached children.")
        
        # If no children are cached, fetch hierarchy from API
        if not children:
            print(f"DEBUG: No cached children, fetching hierarchy for {space_id}")
            asyncio.create_task(self.worker.fetch_space_hierarchy(space_id))
        else:
            # Filter room model to show only these children
            self.room_model.filter_by_space(children)
    
    @Slot(str, list)
    def on_space_hierarchy_updated(self, space_id, children):
        """Handle space hierarchy update from API."""
        print(f"DEBUG: GUI space hierarchy updated: {space_id} -> {children}")
        # If we are currently filtering by this space, update the model
        # (This is simplified - in reality you might be several levels deep)
        if space_id == self.current_space_id:
            if children:
                self.room_model.filter_by_space(children)
            else:
                print(f"DEBUG: Space has no children, showing all rooms")
                self.room_model.clear_filter()

    def resizeEvent(self, event):
        """Force re-layout of message view on window resize to fix multi-line heights."""
        super().resizeEvent(event)
        if hasattr(self, 'message_view'):
            # This triggers re-calculation of sizeHints
            self.message_view.doItemsLayout()
