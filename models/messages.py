from utils.qt import QtCore, QtGui
from typing import List, Any
from datetime import datetime
import re
import zlib
import colorsys

class MessageModel(QtCore.QAbstractListModel):
    """
    A highly optimized model for storing chat messages.
    Uses a simple python list explicitly to keep RAM low.
    """
    
    # Custom Roles
    RawEventRole = QtCore.Qt.UserRole + 1
    SenderRole = QtCore.Qt.UserRole + 2
    TimestampRole = QtCore.Qt.UserRole + 4
    ImageUrlRole = QtCore.Qt.UserRole + 5  # For image messages
    ReplyParentRole = QtCore.Qt.UserRole + 6 # To find original message for jump

    def __init__(self, worker=None, parent=None):
        super().__init__(parent)
        self.worker = worker
        self._rooms_messages = {} # {room_id: [events]}
        self._current_room_id = None
        self._event_ids = set()
        self._expanded_quotes = set() # {event_id}
        self.MAX_MESSAGES = 200

    def set_current_room(self, room_id):
        print(f"DEBUG: MessageModel set_current_room: {room_id}")
        self.beginResetModel()
        self._current_room_id = room_id
        self.endResetModel()

    def _format_body(self, event):
        """Extract and style body, handling replies gracefully."""
        # Check for formatted body (HTML) first
        content = getattr(event, 'source', {}).get('content', {})
        formatted_body = content.get('formatted_body')
        body = content.get('body', getattr(event, 'body', '[No Content]'))
        
        # Detect if it's a Matrix reply
        # Matrix replies in plain text start with "> <@user:server> ..."
        # In HTML they are wrapped in <mx-reply>
        
        is_reply = False
        reply_user = ""
        quote_text = ""
        actual_msg = body

        if formatted_body and "<mx-reply>" in formatted_body:
            is_reply = True
            # Simple regex to extract the quoted part and the actual message
            match = re.search(r'<mx-reply><blockquote>(.*?)</blockquote></mx-reply>(.*)', formatted_body, re.DOTALL)
            if match:
                quote_html = match.group(1)
                actual_msg_html = match.group(2)
                
                # Try to find user MXID specifically (starts with @)
                user_match = re.search(r'<a href="https://matrix.to/#/(@.*?)">', quote_html)
                if user_match:
                    reply_user_id = user_match.group(1)
                    reply_user = reply_user_id
                    if self.worker and reply_user_id in self.worker.member_names:
                        reply_user = self.worker.member_names[reply_user_id]
                    elif reply_user_id.startswith('@'):
                        reply_user = reply_user_id[1:].split(':')[0]
                
                # Strip tags but preserve common line breaks as newlines
                clean_quote = quote_html.replace("<br>", "\n").replace("<br/>", "\n").replace("</div>", "\n")
                quote_text = re.sub('<[^<]+?>', '', clean_quote).strip()
                
                # Common Matrix boilerplate: "In reply to @user:server" or "In reply to Display Name"
                # Remove "In reply to" prefix if it exists to keep it clean
                if quote_text.lower().startswith("in reply to"):
                    # Find first colon or newline to strip header
                    if ":" in quote_text:
                        parts = quote_text.split(":", 1)
                        # The part before the colon is the "In reply to..." header
                        # The part after is the message
                        quote_text = parts[1].strip()
                    elif "\n" in quote_text:
                        parts = quote_text.split("\n", 1)
                        quote_text = parts[1].strip()
                    else:
                        # Fallback: remove "In reply to" and hope for the best
                        quote_text = quote_text[11:].strip()
                
                # Final cleanup: if it still starts with the user ID/name, strip it
                if reply_user and quote_text.startswith(reply_user):
                    quote_text = quote_text[len(reply_user):].lstrip(': ').strip()
                
                # Strip matrix.org if it leaks at the start (common in replies)
                if quote_text.startswith("matrix.org"):
                    quote_text = quote_text[10:].lstrip().strip()
                
                actual_msg = actual_msg_html
        
        elif body.startswith("> <@"):
            # Plain text fallback detection
            lines = body.split('\n')
            if len(lines) >= 3 and lines[0].startswith("> <@"):
                is_reply = True
                header = lines[0][2:] # strip "> "
                reply_user_id = header.split('>')[0] if '>' in header else header
                reply_user = reply_user_id
                if self.worker and reply_user_id in self.worker.member_names:
                    reply_user = self.worker.member_names[reply_user_id]
                elif reply_user_id.startswith('@'):
                    reply_user = reply_user_id[1:].split(':')[0]
                
                quote_text = lines[1][2:] if len(lines) > 1 and lines[1].startswith("> ") else lines[1]
                # Strip matrix.org leakage in plain text too
                if quote_text.startswith("matrix.org"):
                    quote_text = quote_text[10:].lstrip().strip()
                    
                actual_msg = "\n".join(lines[2:]).strip()

        if is_reply:
            event_id = getattr(event, 'event_id', None)
            is_expanded = event_id in self._expanded_quotes
            
            # Truncate if more than 2 lines OR more than 150 characters and not expanded
            lines = [l for l in quote_text.split('\n') if l.strip()]
            has_too_many_lines = len(lines) > 2
            is_too_long = len(quote_text) > 150
            has_more = has_too_many_lines or is_too_long
            
            display_quote = quote_text
            if has_more and not is_expanded:
                if has_too_many_lines:
                    display_quote = "\n".join(lines[:2]).strip()
                elif is_too_long:
                    display_quote = quote_text[:147].strip()
                
                if not display_quote.endswith('...'):
                    display_quote += "..."
            
            # Build a nice HTML block for the reply
            # font size='3' is closer to normal text, size='2' was a bit small
            # We add a small hint if it's expandable
            expand_hint = " <font color='#888888' size='1'>(Click to expand)</font>" if has_more and not is_expanded else ""
            
            reply_html = (
                f"<div style='background-color: #f4f4f4; border-left: 4px solid #dddddd; margin-bottom: 5px; padding: 6px;'>"
                f"<font color='#555555'><b>{reply_user}</b>: {display_quote}{expand_hint}</font>"
                f"</div>"
                f"<div>{actual_msg}</div>"
            )
            return reply_html
        
        return body

    def toggle_quote_expansion(self, index):
        """Toggle expansion state for a quote at a given index."""
        if not index.isValid():
            return
            
        messages = self._rooms_messages.get(self._current_room_id, [])
        row = index.row()
        if row >= len(messages):
            return
            
        event = messages[row]
        event_id = getattr(event, 'event_id', None)
        if not event_id:
            return
            
        if event_id in self._expanded_quotes:
            self._expanded_quotes.remove(event_id)
        else:
            self._expanded_quotes.add(event_id)
            
        # Notify view of change
        self.dataChanged.emit(index, index)

    def get_row_by_event_id(self, event_id):
        """Find the row index for a specific event ID in current room."""
        if not event_id or not self._current_room_id:
            return -1
            
        messages = self._rooms_messages.get(self._current_room_id, [])
        for i, ev in enumerate(messages):
            if getattr(ev, 'event_id', None) == event_id:
                return i
        return -1

    def _get_user_color_hex(self, user_id):
        """Generate a deterministic, high-contrast color using discrete hue segments."""
        if not user_id:
            return "#888888"
            
        # Use adler32 for a simple deterministic hash
        u_hash = zlib.adler32(user_id.encode('utf-8'))
        
        # 16-Segment Discrete Hue: 
        # Divide 360 degrees into 16 sectors (22.5 degrees each)
        # This ensures users are mathematically spread across the color wheel
        sector = u_hash % 16
        hue = (sector * 22.5) / 360.0
        
        # Saturation: 80% for high vibrancy
        saturation = 0.80
        
        # Lightness: 45% is the sweet spot for both light and dark themes
        lightness = 0.45
        
        # Convert HLS to RGB
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        
        # Convert to hex
        return "#{:02x}{:02x}{:02x}".format(int(r*255), int(g*255), int(b*255))

    def rowCount(self, parent=QtCore.QModelIndex()):
        if not self._current_room_id:
            return 0
        return len(self._rooms_messages.get(self._current_room_id, []))

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or not self._current_room_id:
            return None
        
        messages = self._rooms_messages.get(self._current_room_id, [])
        row = index.row()
        if row >= len(messages):
            return None
        
        event = messages[row]
        
        # Efficiently return data based on role
        if role == QtCore.Qt.DisplayRole:
            # Format: "[HH:MM] Sender: Message"
            user_id = getattr(event, 'sender', 'Unknown')
            sender = user_id
            if self.worker and user_id in self.worker.member_names:
                sender = self.worker.member_names[user_id]
            elif user_id.startswith('@') and ':' in user_id:
                # Fallback to localpart for cleaner look
                sender = user_id[1:].split(':')[0]
            
            # 1. Get Timestamp
            ts_ms = getattr(event, 'server_timestamp', 0)
            time_str = ""
            if ts_ms:
                dt = datetime.fromtimestamp(ts_ms / 1000.0)
                time_str = dt.strftime("%H:%M")
            
            # 2. Pick a color for the user based on their ID
            user_color = self._get_user_color_hex(user_id)
            
            # 3. Handle message body (with reply formatting)
            body = self._format_body(event)
            
            # 4. Check if this is an image message
            msgtype = None
            if hasattr(event, 'msgtype'):
                msgtype = event.msgtype
            elif hasattr(event, 'source'):
                msgtype = event.source.get('content', {}).get('msgtype')

            image_icon = "📷 " if msgtype == 'm.image' else ""
            
            # 5. Combine into HTML
            return (
                f"<font color='#888888' size='2'>[{time_str}]</font> "
                f"<font color='{user_color}'><b>{sender}</b></font>: "
                f"{image_icon}{body}"
            )
            
        elif role == self.RawEventRole:
            return event
            
        elif role == self.SenderRole:
            return getattr(event, 'sender', 'Unknown')
            
        elif role == self.TimestampRole:
            return getattr(event, 'server_timestamp', None)
        
        elif role == self.ImageUrlRole:
            if hasattr(event, 'url'):
                return event.url
            elif hasattr(event, 'source'):
                content = event.source.get('content', {})
                return content.get('url')
            return None
        
        elif role == self.ReplyParentRole:
            # Matrix stores reply info in content.m.relates_to
            content = getattr(event, 'source', {}).get('content', {})
            relates = content.get('m.relates_to', {})
            # Look for in_reply_to or pooled relation
            parent = relates.get('m.in_reply_to', {}).get('event_id')
            if not parent and relates.get('rel_type') == 'm.thread':
                parent = relates.get('event_id')
            return parent
        
        return None

    def add_event(self, event):
        # Deduplicate
        event_id = getattr(event, 'event_id', None)
        if event_id and event_id in self._event_ids:
            return
        
        if event_id:
            self._event_ids.add(event_id)
            
        room_id = getattr(event, 'room_id', None)
        if not room_id:
            return
            
        if room_id not in self._rooms_messages:
            self._rooms_messages[room_id] = []
            
        msgs = self._rooms_messages[room_id]
        is_current = (room_id == self._current_room_id)
        
        # Append new message
        if is_current:
            self.beginInsertRows(QtCore.QModelIndex(), len(msgs), len(msgs))
            
        msgs.append(event)
        
        if is_current:
            self.endInsertRows()
            
        # Truncate if over limit
        if len(msgs) > self.MAX_MESSAGES:
            if is_current:
                self.beginRemoveRows(QtCore.QModelIndex(), 0, 0)
            
            old_event = msgs.pop(0)
            # Remove from dedup set too
            old_id = getattr(old_event, 'event_id', None)
            if old_id in self._event_ids:
                self._event_ids.remove(old_id)
                
            if is_current:
                self.endRemoveRows()

    def prepend_batch(self, events: List[Any]):
        if not events:
            return
            
        # Filter duplicates and check room
        room_id = self._current_room_id # Prepended events are always for current room in our GUI
        if not room_id:
            return
            
        if room_id not in self._rooms_messages:
            self._rooms_messages[room_id] = []
            
        msgs = self._rooms_messages[room_id]
        
        unique_events = []
        for e in events:
            # Ensure room_id is set
            if not hasattr(e, 'room_id') or not e.room_id:
                try: e.room_id = room_id
                except: pass
                
            eid = getattr(e, 'event_id', None)
            if eid and eid not in self._event_ids:
                unique_events.append(e)
                self._event_ids.add(eid)
            elif not eid:
                unique_events.append(e)
                
        if not unique_events:
            return

        # Simplified: Reset model for large history prepends to be safe
        self.beginResetModel()
        # History events (prepended) should be OLDER, so they go at the start
        msgs[0:0] = unique_events
        
        # Truncate if over limit (remove oldest from start)
        while len(msgs) > self.MAX_MESSAGES:
            removed = msgs.pop(0)
            rid = getattr(removed, 'event_id', None)
            if rid in self._event_ids:
                self._event_ids.remove(rid)
                
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._rooms_messages.clear()
        self._event_ids.clear()
        self.endResetModel()
