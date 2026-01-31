import asyncio
import logging
from nio import AsyncClient, LoginResponse
from typing import Optional
from utils.qt import QtCore, Signal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MatrixClient")

class MatrixWorker(QtCore.QObject):
    """
    Background worker for Matrix Protocol interactions.
    Runs completely in the asyncio event loop, communicating with Qt via Signals.
    """
    # Signals to update UI
    login_success = Signal(str, str)  # user_id, device_id
    login_failed = Signal(str)
    sync_event = Signal(object)  # Emits nio Event objects
    room_list_updated = Signal(str, str)  # room_id, display_name
    space_list_updated = Signal(str, str)  # space_id, display_name
    history_batch_loaded = Signal(str, list)  # room_id, events
    space_hierarchy_updated = Signal(str, list)  # space_id, [child_room_ids]
    join_result = Signal(bool, str)  # success, message (room_id or error)
    room_removed = Signal(str)  # room_id to remove from room list (if it's actually a space)

    def __init__(self):
        super().__init__()
        self.client: Optional[AsyncClient] = None
        self.should_sync = False
        # Track Space -> [Room IDs] mapping
        self.space_children = {}  # {space_id: [child_room_id, ...]}
        self.room_spaces = {}  # {room_id: [parent_space_id, ...]} for reverse lookup
        self.room_history_tokens = {} # {room_id: "next_batch_token"} for backfill
        self.member_names = {} # {user_id: display_name} global cache for simplicity

    async def login(self, homeserver: str, username: str, password: str):
        """
        Attempts to login to the Matrix homeserver.
        """
        print(f"DEBUG: Attempting login to {homeserver} as {username}")
        logger.info(f"Connecting to {homeserver}...")
        self.client = AsyncClient(homeserver, username)
        
        try:
            print("DEBUG: Sending login request...")
            resp = await self.client.login(password)
            print(f"DEBUG: Login response received: {type(resp)}")
            
            if isinstance(resp, LoginResponse):
                logger.info(f"Login successful: {resp.user_id}")
                self.login_success.emit(resp.user_id, resp.device_id)
                
                # Start sync loop
                self.should_sync = True
                asyncio.create_task(self.sync_forever())
            else:
                logger.error(f"Login failed: {resp}")
                print(f"DEBUG: Login FAILED: {resp}")
                self.login_failed.emit(str(resp))
                await self.client.close()
                self.client = None

        except Exception as e:
            logger.exception("Login exception")
            print(f"DEBUG: Login CRASHED: {e}")
            self.login_failed.emit(str(e))
            if self.client:
                await self.client.close()
                self.client = None

    async def sync_forever(self):
        """
        Continuous sync loop.
        """
        logger.info("Starting sync loop...")
        print("DEBUG: Sync loop started")
        
        # Initial sync might be heavy, so we want full_state for room names first time
        first_sync = True
        
        while self.should_sync and self.client:
            try:
                # Sync with a timeout of 30s
                # full_state=True calls are expensive, use sparingly.
                # standard sync will return changed state.
                print(f"DEBUG: Calling sync(full_state={first_sync})...")
                sync_response = await self.client.sync(timeout=30000, full_state=first_sync)
                print(f"DEBUG: Sync returned. Next Batch: {sync_response.next_batch}")
                first_sync = False
                
                # Process joined rooms
                if not sync_response.rooms.join:
                    print("DEBUG: No joined rooms in this sync.")
                
                for room_id, room_info in sync_response.rooms.join.items():
                    print(f"DEBUG: Processing room {room_id}")
                    
                    # Determine if it is a Space or a Room
                    room_data = self.client.rooms.get(room_id)
                    display_name = room_id
                    is_space = False
                    
                    if room_data:
                        display_name = room_data.display_name
                        
                        # Check if this room is a Space
                        # MatrixRoom has a room_type property that should be 'm.space' for spaces
                        room_type = getattr(room_data, 'room_type', None)
                        print(f"DEBUG: Room {room_id} has room_type: {room_type}")
                        
                        if room_type == 'm.space':
                            is_space = True
                            print(f"DEBUG: ✓ Detected Space via room_type: {room_id}")
                    
                    # Also check state events as fallback
                    if not is_space and hasattr(room_info, 'state') and room_info.state:
                        print(f"DEBUG: Checking state events for {room_id}, has {len(room_info.state)} events")
                        for state_event in room_info.state:
                            event_type = getattr(state_event, 'type', None)
                            if event_type == 'm.room.create':
                                content = getattr(state_event, 'content', {})
                                print(f"DEBUG: Found m.room.create for {room_id}, content: {content}")
                                if isinstance(content, dict) and content.get('type') == 'm.space':
                                    is_space = True
                                    print(f"DEBUG: ✓ Detected Space via state event: {room_id}")
                    
                    # Track space children relationships (check state events)
                    if hasattr(room_info, 'state') and room_info.state:
                        for state_event in room_info.state:
                            event_type = getattr(state_event, 'type', None)
                            if event_type == 'm.space.child':
                                state_key = getattr(state_event, 'state_key', None)
                                if state_key:  # state_key is the child room ID
                                    if room_id not in self.space_children:
                                        self.space_children[room_id] = []
                                    if state_key not in self.space_children[room_id]:
                                        self.space_children[room_id].append(state_key)
                                    
                                    # Reverse mapping
                                    if state_key not in self.room_spaces:
                                        self.room_spaces[state_key] = []
                                    if room_id not in self.room_spaces[state_key]:
                                        self.room_spaces[state_key].append(room_id)
                                    
                                    print(f"DEBUG: Space {room_id} has child {state_key}")
                            
                            elif event_type == 'm.room.member':
                                # Capture display names
                                user_id = getattr(state_event, 'state_key', None)
                                content = getattr(state_event, 'content', {})
                                m_display_name = content.get('displayname')
                                if user_id and m_display_name:
                                    self.member_names[user_id] = m_display_name
                                    # print(f"DEBUG: Captured display name for {user_id}: {m_display_name}")
                    
                    # Store prev_batch token for first backfill if we don't have one
                    if hasattr(room_info, 'timeline') and hasattr(room_info.timeline, 'prev_batch'):
                        if room_id not in self.room_history_tokens:
                            self.room_history_tokens[room_id] = room_info.timeline.prev_batch
                            print(f"DEBUG: Stored initial backfill token for {room_id}: {room_info.timeline.prev_batch}")
                    
                    # Final safety check for display_name
                    if not display_name:
                        display_name = room_id

                    if is_space:
                         print(f"DEBUG: Emitting space_list_updated for {room_id}")
                         self.room_removed.emit(room_id) # Ensure it's removed from rooms if it was there
                         self.space_list_updated.emit(room_id, display_name)
                         # Also try to fetch hierarchy immediately for a better initial experience
                         asyncio.create_task(self.fetch_space_hierarchy(room_id))
                    else:
                         print(f"DEBUG: Emitting room_list_updated for {room_id}")
                         self.room_list_updated.emit(room_id, display_name)
                    
                    # Emit timeline events
                    for event in room_info.timeline.events:
                        # Ensure we inject the room_id if missing
                        try:
                            if not hasattr(event, 'room_id') or not event.room_id:
                                event.room_id = room_id
                        except AttributeError:
                            # Some nio events are immutable (e.g. namedtuples)
                            # We'll just emit them and rely on GUI or better injection
                            pass
                        
                        self.sync_event.emit(event)
                
            except Exception as e:
                logger.error(f"Sync error: {e}")
                print(f"DEBUG SYNC ERROR: {e}")
                await asyncio.sleep(5) # Backoff on error

    async def send_message(self, room_id: str, text: str):
        if self.client and room_id:
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": text
                }
            )

    async def join_room(self, room_id_or_alias: str):
        """
        Join a room or space by its ID or alias.
        """
        if not self.client:
            return
        
        print(f"DEBUG: Attempting to join {room_id_or_alias}")
        try:
            resp = await self.client.join(room_id_or_alias)
            if hasattr(resp, 'room_id'):
                room_id = resp.room_id
                print(f"DEBUG: Successfully joined {room_id}")
                self.join_result.emit(True, room_id)
                # Proactively discover room info to show it immediately
                asyncio.create_task(self._proactive_room_discovery(room_id))
                # Fallback: trigger a sync too
                asyncio.create_task(self.client.sync(timeout=0))
            else:
                error_msg = str(resp)
                print(f"DEBUG: Join failed: {error_msg}")
                self.join_result.emit(False, error_msg)
        except Exception as e:
            print(f"DEBUG: Join exception: {e}")
            self.join_result.emit(False, str(e))

    async def _proactive_room_discovery(self, room_id: str):
        """
        Fetch room name and type immediately after joining.
        """
        if not self.client:
            return
            
        print(f"DEBUG: Proactive discovery for {room_id}")
        try:
            # Try to get room name
            name_resp = await self.client.room_get_state_event(room_id, "m.room.name")
            name = ""
            if hasattr(name_resp, 'content'):
                name = name_resp.content.get('name', '')
            
            if not name:
                alias_resp = await self.client.room_get_state_event(room_id, "m.room.canonical_alias")
                if hasattr(alias_resp, 'content'):
                    name = alias_resp.content.get('alias', '')
            
            display_name = name or room_id
            
            # Try to get room type (Space check)
            create_resp = await self.client.room_get_state_event(room_id, "m.room.create")
            is_space = False
            if hasattr(create_resp, 'content'):
                is_space = (create_resp.content.get('type') == 'm.space')
            
            if is_space:
                print(f"DEBUG: Proactive discovery: {room_id} IS a Space.")
                self.room_removed.emit(room_id)
                self.space_list_updated.emit(room_id, display_name)
                asyncio.create_task(self.fetch_space_hierarchy(room_id))
            else:
                print(f"DEBUG: Proactive discovery: {room_id} is a regular Room.")
                self.room_list_updated.emit(room_id, display_name)
                
        except Exception as e:
            print(f"DEBUG: Proactive discovery failed for {room_id}: {e}")

    async def leave_room(self, room_id: str):
        """
        Leave a room or space.
        """
        if not self.client or not room_id:
            return
            
        print(f"DEBUG: Attempting to leave {room_id}")
        try:
            resp = await self.client.room_leave(room_id)
            # nio returns an empty RoomLeaveResponse on success
            print(f"DEBUG: Leave response for {room_id}: {resp}")
            # The sync loop will see the leave and we should probably remove it
            self.room_removed.emit(room_id)
        except Exception as e:
            print(f"DEBUG: Leave exception for {room_id}: {e}")

    async def load_room_history(self, room_id: str):
        """
        Load older messages (backfill) for a room.
        """
        if not self.client:
            return
        
        # Get the token for backfill
        token = self.room_history_tokens.get(room_id, "")
        
        print(f"DEBUG: Loading history for {room_id} (token: {token})")
        
        try:
            # Request older messages
            resp = await self.client.room_messages(
                room_id=room_id,
                start=token,
                limit=100,
                direction="b"
            )
            
            if hasattr(resp, 'chunk'):
                print(f"DEBUG: Backfill returned {len(resp.chunk)} events.")
                
                # Update token for next backfill
                if hasattr(resp, 'end'):
                    self.room_history_tokens[room_id] = resp.end
                
                # Inject room_id if missing
                final_chunk = []
                for e in resp.chunk:
                    try:
                        if not hasattr(e, 'room_id') or not e.room_id:
                            e.room_id = room_id
                    except AttributeError:
                        pass
                    final_chunk.append(e)
                    
                # room_messages with direction="b" returns newest first.
                # We reverse it to make it oldest-first for the model's prepend call.
                self.history_batch_loaded.emit(room_id, list(reversed(final_chunk)))
            else:
                print(f"DEBUG: Backfill failed or returned no chunk: {resp}")


        except Exception as e:
            logger.error(f"Backfill error: {e}")
            print(f"DEBUG: Backfill EXCEPTION: {e}")
    
    async def fetch_space_hierarchy(self, space_id: str):
        """
        Fetch the hierarchy of a Space to get its children.
        Uses the /hierarchy endpoint.
        """
        if not self.client:
            return
        
        print(f"DEBUG: Fetching hierarchy for space {space_id}")
        
        try:
            # Use the rooms/hierarchy endpoint
            # Note: matrix-nio may not have a direct method for this, so we use HTTP API
            url = f"{self.client.homeserver}/_matrix/client/v1/rooms/{space_id}/hierarchy"
            
            # Make authenticated request
            headers = {
                "Authorization": f"Bearer {self.client.access_token}",
                "Content-Type": "application/json"
            }
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"DEBUG: Hierarchy response: {data}")
                        
                        # Parse children from response
                        children = []
                        rooms = data.get('rooms', [])
                        
                        for room in rooms:
                            room_id = room.get('room_id')
                            if not room_id:
                                continue
                                
                            # Get room name/alias from hierarchy data
                            name = room.get('name') or room.get('canonical_alias') or room_id
                            
                            # Skip the space itself for the children list
                            if room_id != space_id:
                                children.append(room_id)
                                # Tell the GUI about this room so it exists in the model even if not yet synced
                                self.room_list_updated.emit(room_id, name)
                        
                        print(f"DEBUG: Found {len(children)} children for space {space_id}")
                        
                        # Update mapping
                        self.space_children[space_id] = children
                        for child_id in children:
                            if child_id not in self.room_spaces:
                                self.room_spaces[child_id] = []
                            if space_id not in self.room_spaces[child_id]:
                                self.room_spaces[child_id].append(space_id)
                        
                        # Emit signal
                        self.space_hierarchy_updated.emit(space_id, children)
                    else:
                        print(f"DEBUG: Hierarchy fetch failed with status {response.status}")
        
        except Exception as e:
            logger.error(f"Space hierarchy fetch error: {e}")
            print(f"DEBUG: Space hierarchy EXCEPTION: {e}")
    
    async def download_image(self, mxc_url: str) -> bytes:
        """
        Download an image from Matrix media repository.
        mxc_url format: mxc://server/media_id
        """
        if not self.client or not mxc_url.startswith("mxc://"):
            return None
        
        try:
            # Parse mxc URL
            # Format: mxc://server_name/media_id
            parts = mxc_url[6:].split("/", 1)
            if len(parts) != 2:
                print(f"DEBUG: Invalid mxc URL: {mxc_url}")
                return None
            
            server_name, media_id = parts
            
            # 1. Try full resolution download first
            print(f"DEBUG: [Final Fix] Downloading {mxc_url}...")
            resp = await self.client.download(server_name, media_id)
            
            if hasattr(resp, 'body') and resp.body:
                print(f"DEBUG: Success: Original image downloaded.")
                return resp.body
            
            # 2. Fallback to thumbnail using library defaults
            print(f"DEBUG: Original failed. Trying thumbnail...")
            try:
                resp = await self.client.thumbnail(
                    server_name, 
                    media_id,
                    width=1280, 
                    height=720
                    # Note: Omitting 'method' to avoid Enum/str conflicts in different nio versions
                )
                
                if hasattr(resp, 'body') and resp.body:
                    print(f"DEBUG: Success: Thumbnail downloaded.")
                    return resp.body
            except Exception as thumb_error:
                print(f"DEBUG: Thumbnail fallback failed: {thumb_error}")
            
            return None
            
            return None
        
        except Exception as e:
            print(f"DEBUG: Image download exception: {e}")
            return None

    async def shutdown(self):
        self.should_sync = False
        if self.client:
            await self.client.close()
            self.client = None
