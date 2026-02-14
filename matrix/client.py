"""
Matrix client wrapper using matrix-nio.

Handles Matrix protocol operations, E2EE, and sync operations.
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from pathlib import Path

from nio import (
    AsyncClient,
    LoginResponse,
    SyncResponse,
    RoomMessageText,
    RoomMessageImage,
    MegolmEvent,
    MatrixRoom,
    LocalProtocolError,
    RoomGetEventError,
    RoomMessagesResponse,
    ProfileGetResponse,
    crypto
)

from config import config
from .storage import CredentialStorage
from .media_manager import MediaManager

logger = logging.getLogger(__name__)


class MatrixClient:
    """Wrapper around nio.AsyncClient with session management."""
    
    def __init__(self, homeserver: Optional[str] = None):
        """Initialize Matrix client.
        
        Args:
            homeserver: Matrix homeserver URL. If None, will load from storage.
        """
        self.homeserver = homeserver
        self.client: Optional[AsyncClient] = None
        self.storage = CredentialStorage()
        self.media_manager = MediaManager()
        
        # Callbacks
        self.on_sync: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        
        self._sync_task: Optional[asyncio.Task] = None
        
        # Performance optimizations
        self._profile_cache: Dict[str, Dict[str, Any]] = {}
        self._profile_requests: Dict[str, asyncio.Task] = {}
        self._profile_cache_path = config.cache_dir / "profiles.json"
        self._load_profile_cache()
    
    def _load_profile_cache(self):
        """Load profile cache from disk."""
        if self._profile_cache_path.exists():
            try:
                import json
                with open(self._profile_cache_path, 'r') as f:
                    self._profile_cache = json.load(f)
                logger.info(f"Loaded {len(self._profile_cache)} profiles from cache")
            except Exception as e:
                logger.error(f"Failed to load profile cache: {e}")
                self._profile_cache = {}

    def _save_profile_cache(self):
        """Save profile cache to disk."""
        try:
            import json
            # Ensure directory exists
            self._profile_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._profile_cache_path, 'w') as f:
                json.dump(self._profile_cache, f)
            logger.debug(f"Saved {len(self._profile_cache)} profiles to cache")
        except Exception as e:
            logger.error(f"Failed to save profile cache: {e}")
    
    async def login(self, username: str, password: str) -> bool:
        """Login with username and password.
        
        Args:
            username: Matrix username (without @)
            password: User password
            
        Returns:
            True if login successful, False otherwise
        """
        if not self.homeserver:
            logger.error("No homeserver specified")
            return False
        
        # Create client
        # Ensure username is passed
        self.client = AsyncClient(
            homeserver=self.homeserver,
            user=username,
            store_path=str(config.store_path)
        )
        
        # Attempt login
        try:
            response = await self.client.login(password=password, device_name="OMOMatrix")
            
            if isinstance(response, LoginResponse):
                logger.info(f"Logged in as {response.user_id}")
                
                # Save credentials
                self.storage.save_credentials(
                    homeserver=self.homeserver,
                    user_id=response.user_id,
                    access_token=response.access_token,
                    device_id=response.device_id
                )
                
                # Setup E2EE if available
                if self.client.should_upload_keys:
                    await self.client.keys_upload()
                
                return True
            else:
                logger.error(f"Login failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def restore_session(self) -> bool:
        """Restore session from stored credentials.
        
        Returns:
            True if session restored, False otherwise
        """
        creds = self.storage.load_credentials()
        
        if not creds:
            logger.info("No stored credentials found")
            return False
        
        self.homeserver = creds['homeserver']
        
        # Create client with stored credentials
        self.client = AsyncClient(
            homeserver=self.homeserver,
            user=creds['user_id'],
            device_id=creds['device_id'],
            store_path=str(config.store_path)
        )
        
        # Restore access token
        self.client.access_token = creds['access_token']
        
        logger.info(f"Restored session for {creds['user_id']}")
        
        # Load encryption keys if available
        if self.client.should_query_keys:
            await self.client.keys_query()
        
        return True
    
    async def logout(self):
        """Logout and clear session."""
        if self.client:
            try:
                await self.client.logout()
            except Exception as e:
                logger.error(f"Logout error: {e}")
            finally:
                await self.client.close()
                self.client = None
        
        # Clear stored credentials
        self.storage.clear_credentials()
        logger.info("Logged out")
    
    async def start_sync(self):
        """Start sync loop to receive events."""
        if not self.client:
            logger.error("Client not initialized")
            return
        
        # Register callbacks
        if self.on_message:
            self.client.add_event_callback(self.on_message, RoomMessageText)
            self.client.add_event_callback(self.on_message, RoomMessageImage)
            self.client.add_event_callback(self.on_message, MegolmEvent)
        
        # Start sync task
        self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def _sync_loop(self):
        """Main sync loop."""
        logger.info("Starting sync loop")
        
        try:
            # Initial sync
            response = await self.client.sync(timeout=30000)
            
            if self.on_sync:
                try:
                    self.on_sync(response if isinstance(response, SyncResponse) else None)
                except Exception as e:
                    logger.error(f"Error in initial on_sync callback: {e}")
            
            # Continuous sync
            while True:
                response = await self.client.sync(timeout=30000)
                
                if isinstance(response, SyncResponse):
                    logger.debug(f"Sync successful, received {len(response.rooms.join)} joined rooms")
                    if self.on_sync:
                        try:
                            self.on_sync(response)
                        except Exception as e:
                            logger.error(f"Error in on_sync callback: {e}")
                else:
                    logger.warning(f"Sync error: {response}")
                
                # Process next sync immediately
                pass
                
        except asyncio.CancelledError:
            logger.info("Sync loop cancelled")
        except Exception as e:
            logger.error(f"Sync loop error: {e}")
    
    async def stop_sync(self):
        """Stop sync loop."""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
    
    async def send_message(self, room_id: str, message: str, reply_to_id: Optional[str] = None, reply_to_body: Optional[str] = None):
        """Send a text message to a room.
        
        Args:
            room_id: Room ID to send message to
            message: Message text
            reply_to_id: Optional event ID to reply to
            reply_to_body: Optional body of the message being replied to
        """
        if not self.client:
            logger.error("Client not initialized")
            return
        
        content = {
            "msgtype": "m.text",
            "body": message
        }
        
        if reply_to_id:
            # We don't prepend the quote to 'body' anymore because modern clients 
            # show it automatically via m.relates_to, and manual prepending 
            # causes double-quotes in some clients.
            content["m.relates_to"] = {
                "m.in_reply_to": {
                    "event_id": reply_to_id
                }
            }
        
        try:
            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
    
    async def join_room(self, room_id_or_alias: str) -> bool:
        """Join a room or space.
        
        Args:
            room_id_or_alias: Room ID or alias (e.g., #room:server.org)
            
        Returns:
            True if joined successfully
        """
        if not self.client:
            return False
        
        try:
            response = await self.client.join(room_id_or_alias)
            return hasattr(response, 'room_id')
        except Exception as e:
            logger.error(f"Failed to join room: {e}")
            return False
    
    async def leave_room(self, room_id: str) -> bool:
        """Leave a room or space.
        
        Args:
            room_id: Room ID to leave
            
        Returns:
            True if left successfully
        """
        if not self.client:
            return False
        
        try:
            await self.client.room_leave(room_id)
            return True
        except Exception as e:
            logger.error(f"Failed to leave room: {e}")
            return False
    
    def get_rooms(self) -> Dict[str, MatrixRoom]:
        """Get all joined rooms.
        
        Returns:
            Dictionary mapping room_id to MatrixRoom
        """
        if not self.client:
            return {}
            
        return self.client.rooms

    def get_hierarchy(self):
        """Build space/room hierarchy using nio's built-in room attributes.
        
        Returns:
            Dictionary containing spaces info, children mapping, top-level spaces and orphans.
        """
        if not self.client:
            return {"spaces": {}, "children": {}, "top_level_spaces": [], "orphans": []}
            
        rooms = self.client.rooms
        joined_ids = set(rooms.keys())
        
        # Identify which rooms are spaces
        spaces_map = {} # room_id -> bool
        for room_id, room in rooms.items():
            # nio's MatrixRoom has a room_type attribute
            spaces_map[room_id] = (room.room_type == "m.space")
            
        # Build relationship maps using nio's built-in children and parents sets
        # nio.rooms.MatrixRoom has .children and .parents which are sets of room_ids
        children_map = {} # parent -> [children]
        parents_map = {} # child -> [parents]
        
        for room_id, room in rooms.items():
            # children and parents are sets of strings (room IDs)
            valid_children = [cid for cid in room.children if cid in joined_ids]
            if valid_children:
                children_map[room_id] = valid_children
                for cid in valid_children:
                    parents_map.setdefault(cid, []).append(room_id)
            
            # We also check room.parents to be safe
            valid_parents = [pid for pid in room.parents if pid in joined_ids]
            for pid in valid_parents:
                parents_map.setdefault(room_id, []).append(pid)
                children_map.setdefault(pid, []).append(room_id)
        
        # Deduplicate and finalize maps
        for k in children_map:
            children_map[k] = list(set(children_map[k]))
        for k in parents_map:
            parents_map[k] = list(set(parents_map[k]))
            
        # Top-level spaces: Spaces that don't have a joined parent
        top_level_spaces = [rid for rid, is_space in spaces_map.items() 
                           if is_space and not parents_map.get(rid)]
        
        # Orphans: Rooms that are not spaces and don't have a joined parent
        orphans = [rid for rid, is_space in spaces_map.items() 
                  if not is_space and not parents_map.get(rid)]
        
        # Sort by name for consistency
        def sort_key(rid):
            room = rooms.get(rid)
            return (room.display_name or rid).lower() if room else rid.lower()
            
        top_level_spaces.sort(key=sort_key)
        orphans.sort(key=sort_key)
        for k in children_map:
            children_map[k].sort(key=sort_key)
            
        return {
            "spaces": spaces_map,
            "children": children_map,
            "top_level_spaces": top_level_spaces,
            "orphans": orphans
        }
    
    async def get_room_messages(self, room_id: str, limit: int = 50, start: Optional[str] = None):
        """Fetch historical messages from a room.
        
        Args:
            room_id: Room ID
            limit: Number of messages to fetch
            start: Pagination token to start from
            
        Returns:
            RoomMessagesResponse or Error
        """
        if not self.client:
            return None
            
        try:
            response = await self.client.room_messages(room_id, start=start, limit=limit)
            
            if isinstance(response, RoomMessagesResponse) and hasattr(response, 'chunk'):
                logger.debug(f"Fetched {len(response.chunk)} messages for room {room_id}")
                # Attempt to decrypt encrypted historical messages
                for event in response.chunk:
                    if isinstance(event, MegolmEvent):
                        try:
                            logger.debug(f"Attempting to decrypt historical event {event.event_id}")
                            # client.decrypt_event returns the decrypted event or raises
                            decrypted_event = self.client.decrypt_event(event)
                            
                            if not isinstance(decrypted_event, MegolmEvent):
                                logger.debug(f"Successfully decrypted historical event {event.event_id}")
                                index = response.chunk.index(event)
                                response.chunk[index] = decrypted_event
                            else:
                                logger.debug(f"Decryption failed for historical event {event.event_id} (still MegolmEvent)")
                        except Exception as e:
                            logger.error(f"Error decrypting historical event {event.event_id}: {e}")
            else:
                logger.warning(f"Room messages response for {room_id} was not RoomMessagesResponse: {response}")
            
            return response
        except Exception as e:
            logger.error(f"Failed to fetch room messages: {e}")
            return None

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Fetch user profile information with caching and request coalescing.
        
        Args:
            user_id: Matrix user ID
            
        Returns:
            Dictionary with displayname and avatar_url
        """
        if not self.client:
            return {}
            
        # Check cache first
        if user_id in self._profile_cache:
            return self._profile_cache[user_id]
            
        # Check if a request is already in progress
        if user_id in self._profile_requests:
            try:
                return await self._profile_requests[user_id]
            except Exception:
                return {}
                
        # Start new request task
        async def _fetch():
            try:
                response = await self.client.get_profile(user_id)
                if isinstance(response, ProfileGetResponse):
                    profile = {
                        "displayname": response.displayname,
                        "avatar_url": response.avatar_url
                    }
                    self._profile_cache[user_id] = profile
                    self._save_profile_cache()
                    return profile
            except Exception as e:
                logger.debug(f"Failed to fetch profile for {user_id}: {e}")
            finally:
                # Remove from active requests
                self._profile_requests.pop(user_id, None)
            return {}

        task = asyncio.create_task(_fetch())
        self._profile_requests[user_id] = task
        return await task
    
    async def close(self):
        """Close the client connection."""
        await self.stop_sync()
        
        if self.client:
            await self.client.close()
            self.client = None
