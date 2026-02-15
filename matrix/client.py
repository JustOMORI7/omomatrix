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
    ToDeviceEvent,
    UnknownEvent,
    UnknownToDeviceEvent,
    KeyVerificationEvent,
    KeyVerificationStart,
    KeyVerificationCancel,
    KeyVerificationKey,
    KeyVerificationMac,
    KeyVerificationAccept,
    RoomKeyRequest,
    crypto
)

from config import config
from .storage import CredentialStorage
from .media_manager import MediaManager

logger = logging.getLogger(__name__)


class MatrixClient:
    """Wrapper around nio.AsyncClient with session management."""
    
    def __init__(self, homeserver: Optional[str] = None):
        self.homeserver = homeserver
        self.client: Optional[AsyncClient] = None
        self.storage = CredentialStorage()
        self.media_manager = MediaManager()
        self.on_sync: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        self.on_verification_event: Optional[Callable] = None 
        self._sync_task: Optional[asyncio.Task] = None
        self.verifications: Dict[str, Any] = {}
        self._profile_cache: Dict[str, Dict[str, Any]] = {}
        self._profile_requests: Dict[str, asyncio.Task] = {}
        self._profile_cache_path = config.cache_dir / "profiles.json"
        self._load_profile_cache()
    
    def _load_profile_cache(self):
        if self._profile_cache_path.exists():
            try:
                import json
                with open(self._profile_cache_path, 'r') as f:
                    self._profile_cache = json.load(f)
            except: self._profile_cache = {}

    def _save_profile_cache(self):
        try:
            import json
            self._profile_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._profile_cache_path, 'w') as f:
                json.dump(self._profile_cache, f)
        except: pass
    
    async def login(self, username: str, password: str) -> bool:
        if not self.homeserver: return False
        self.client = AsyncClient(homeserver=self.homeserver, user=username, store_path=str(config.store_path))
        try:
            response = await self.client.login(password=password, device_name="OMOMatrix")
            if isinstance(response, LoginResponse):
                self.storage.save_credentials(homeserver=self.homeserver, user_id=response.user_id, access_token=response.access_token, device_id=response.device_id)
                self.client.load_store()
                if self.client.should_upload_keys: await self.client.keys_upload()
                return True
            return False
        except: return False
    
    async def restore_session(self) -> bool:
        creds = self.storage.load_credentials()
        if not creds: return False
        
        # FIX: Strip any spaces that might have been saved in the database
        user_id = creds['user_id'].strip()
        device_id = creds['device_id'].strip()
        self.homeserver = creds['homeserver'].strip()
        
        # If we found spaces, save the cleaned version back to database
        if user_id != creds['user_id'] or device_id != creds['device_id']:
            logger.info("Cleaning up whitespace in stored credentials")
            self.storage.save_credentials(
                self.homeserver, user_id, creds['access_token'], device_id
            )

        self.client = AsyncClient(
            homeserver=self.homeserver, 
            user=user_id, 
            device_id=device_id, 
            store_path=str(config.store_path)
        )
        self.client.access_token = creds['access_token']
        self.client.user_id = user_id
        self.client.load_store()
        if self.client.should_query_keys: await self.client.keys_query()
        return True
    
    async def logout(self):
        if self.client:
            try: await self.client.logout()
            except: pass
            finally: await self.client.close(); self.client = None
        self.storage.clear_credentials()
    
    async def start_sync(self):
        if not self.client: return
        if self.on_message:
            self.client.add_event_callback(self.on_message, RoomMessageText)
            self.client.add_event_callback(self.on_message, RoomMessageImage)
            self.client.add_event_callback(self.on_message, MegolmEvent)
        
        # E2EE Callbacks
        self.client.add_to_device_callback(self.handle_verification_event, ToDeviceEvent)
        self.client.add_to_device_callback(self.handle_key_request, RoomKeyRequest)
        
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def handle_key_request(self, event: RoomKeyRequest):
        """Handle incoming key requests from our other devices."""
        if not self.client: return
        # Automatically share keys if the requesting device is verified
        if self.client.device_store[event.sender][event.requesting_device_id].verified:
            logger.info(f"Automatically sharing keys with verified device {event.requesting_device_id}")
            await self.client.continue_key_share(event)

    async def handle_verification_event(self, event):
        sender = event.sender.strip() if event.sender else None
        
        if isinstance(event, UnknownToDeviceEvent):
            content = event.source.get("content", {})
            tx_id = content.get("transaction_id")
            if not tx_id: return
            
            if event.type == "m.key.verification.request":
                from_device = content.get("from_device", "*").strip()
                self.verifications[tx_id] = {"state": "requested", "sender": sender, "device": from_device}
                if self.on_verification_event: self.on_verification_event("request", tx_id, sender, from_device)
            elif event.type == "m.key.verification.done":
                if self.on_verification_event: self.on_verification_event("mac", tx_id, sender, "*")
            return

        if not isinstance(event, KeyVerificationEvent): return
        tx_id = event.transaction_id

        if isinstance(event, KeyVerificationStart):
            if tx_id not in self.verifications or not hasattr(self.verifications[tx_id], 'get_emoji'):
                self.verifications[tx_id] = self.client.key_verifications[tx_id]
            from_device = getattr(event, 'from_device', "*").strip()
            if self.on_verification_event: self.on_verification_event("start", tx_id, sender, from_device)
        elif isinstance(event, KeyVerificationCancel):
            self.verifications.pop(tx_id, None)
            if self.on_verification_event: self.on_verification_event("cancel", tx_id, sender, "*")
        elif isinstance(event, (KeyVerificationKey, KeyVerificationAccept, KeyVerificationMac)):
            state = "key" if isinstance(event, KeyVerificationKey) else ("accept" if isinstance(event, KeyVerificationAccept) else "mac")
            if self.on_verification_event: self.on_verification_event(state, tx_id, sender, "*")

    async def accept_verification_request(self, transaction_id: str, sender: str, device_id: str):
        if not self.client: return
        content = {"transaction_id": transaction_id, "methods": ["m.sas.v1"], "from_device": self.client.device_id}
        try:
            from nio.event_builders.direct_messages import ToDeviceMessage
            msg = ToDeviceMessage("m.key.verification.ready", sender.strip(), device_id.strip(), content)
            self.client.outgoing_to_device_messages.append(msg)
            await self.client.send_to_device_messages()
        except: pass

    async def start_verification(self, user_id: str, device_id: str):
        if not self.client: return
        response = await self.client.verify_device(user_id.strip(), device_id.strip())
        if response:
            self.verifications[response] = self.client.key_verifications[response]
            return response
        return None

    async def accept_verification(self, transaction_id: str):
        if transaction_id in self.verifications:
            await self.client.accept_key_verification(transaction_id)
            sas = self.verifications[transaction_id]
            try:
                from nio.event_builders.direct_messages import ToDeviceMessage
                if hasattr(sas, 'accept_verification'):
                    self.client.outgoing_to_device_messages.append(sas.accept_verification())
                if hasattr(sas, 'share_key'):
                    self.client.outgoing_to_device_messages.append(sas.share_key())
                await self.client.send_to_device_messages()
            except: pass

    async def confirm_sas(self, transaction_id: str):
        if transaction_id in self.verifications:
            sas = self.verifications[transaction_id]
            sas.accept_sas()
            self.client.outgoing_to_device_messages.append(sas.get_mac())
            await self.client.send_to_device_messages()
            if sas.verified:
                await self.send_verification_done(transaction_id, sas.other_olm_device.user_id, sas.other_olm_device.device_id)

    async def send_verification_done(self, transaction_id: str, sender: str, device_id: str):
        try:
            from nio.event_builders.direct_messages import ToDeviceMessage
            msg = ToDeviceMessage("m.key.verification.done", sender, device_id, {"transaction_id": transaction_id})
            self.client.outgoing_to_device_messages.append(msg)
            await self.client.send_to_device_messages()
        except: pass

    async def cancel_verification(self, transaction_id: str):
        if transaction_id in self.verifications:
            try: await self.client.cancel_key_verification(transaction_id)
            except: pass
            self.verifications.pop(transaction_id, None)

    def get_sas_emojis(self, transaction_id: str):
        if transaction_id in self.verifications:
            sas = self.verifications[transaction_id]
            if hasattr(sas, 'get_emoji') and getattr(sas, 'chosen_key_agreement', None):
                try: return sas.get_emoji()
                except: return None
        return None
    
    async def _sync_loop(self):
        try:
            # We must use 'since' to acknowledge to-device messages
            response = await self.client.sync(timeout=30000)
            while True:
                response = await self.client.sync(timeout=30000, since=response.next_batch)
                if isinstance(response, SyncResponse):
                    if self.on_sync: self.on_sync(response)
                    # Background E2EE tasks
                    if self.client.should_query_keys: await self.client.keys_query()
                    if self.client.should_upload_keys: await self.client.keys_upload()
        except Exception as e:
            logger.error(f"Sync loop error: {e}")
    
    async def stop_sync(self):
        if self._sync_task:
            self._sync_task.cancel()
            try: await self._sync_task
            except: pass
            self._sync_task = None
    
    async def send_message(self, room_id: str, message: str, reply_to_id: Optional[str] = None, reply_to_body: Optional[str] = None):
        if not self.client: return
        content = {"msgtype": "m.text", "body": message}
        if reply_to_id: content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to_id}}
        try: await self.client.room_send(room_id=room_id, message_type="m.room.message", content=content)
        except: pass
    
    async def join_room(self, room_id_or_alias: str) -> bool:
        if not self.client: return False
        try:
            response = await self.client.join(room_id_or_alias)
            return hasattr(response, 'room_id')
        except: return False
    
    def get_rooms(self) -> Dict[str, MatrixRoom]:
        return self.client.rooms if self.client else {}

    def get_hierarchy(self):
        if not self.client: return {"spaces": {}, "children": {}, "top_level_spaces": [], "orphans": []}
        rooms = self.client.rooms
        joined_ids = set(rooms.keys())
        spaces_map = {rid: (room.room_type == "m.space") for rid, room in rooms.items()}
        children_map, parents_map = {}, {}
        for room_id, room in rooms.items():
            valid_children = [cid for cid in room.children if cid in joined_ids]
            if valid_children:
                children_map[room_id] = valid_children
                for cid in valid_children: parents_map.setdefault(cid, []).append(room_id)
            valid_parents = [pid for pid in room.parents if pid in joined_ids]
            for pid in valid_parents:
                parents_map.setdefault(room_id, []).append(pid)
                children_map.setdefault(pid, []).append(room_id)
        for k in children_map: children_map[k] = list(set(children_map[k]))
        for k in parents_map: parents_map[k] = list(set(parents_map[k]))
        top_level_spaces = sorted([rid for rid, is_space in spaces_map.items() if is_space and not parents_map.get(rid)], key=lambda rid: (rooms.get(rid).display_name or rid).lower())
        orphans = sorted([rid for rid, is_space in spaces_map.items() if not is_space and not parents_map.get(rid)], key=lambda rid: (rooms.get(rid).display_name or rid).lower())
        for k in children_map: children_map[k].sort(key=lambda rid: (rooms.get(rid).display_name or rid).lower() if rooms.get(rid) else rid.lower())
        return {"spaces": spaces_map, "children": children_map, "top_level_spaces": top_level_spaces, "orphans": orphans}
    
    async def get_room_messages(self, room_id: str, limit: int = 50, start: Optional[str] = None):
        if not self.client: return None
        try:
            response = await self.client.room_messages(room_id, start=start, limit=limit)
            if isinstance(response, RoomMessagesResponse) and hasattr(response, 'chunk'):
                for event in response.chunk:
                    if isinstance(event, MegolmEvent):
                        try:
                            decrypted = self.client.decrypt_event(event)
                            if not isinstance(decrypted, MegolmEvent):
                                index = response.chunk.index(event)
                                response.chunk[index] = decrypted
                            else:
                                # Still undecryptable, request keys from other devices
                                await self.client.request_room_key(event)
                        except: pass
            return response
        except: return None

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        if not self.client: return {}
        if user_id in self._profile_cache: return self._profile_cache[user_id]
        if user_id in self._profile_requests:
            try: return await self._profile_requests[user_id]
            except: return {}
        async def _fetch():
            try:
                response = await self.client.get_profile(user_id)
                if isinstance(response, ProfileGetResponse):
                    profile = {"displayname": response.displayname, "avatar_url": response.avatar_url}
                    self._profile_cache[user_id] = profile
                    self._save_profile_cache()
                    return profile
            except: pass
            finally: self._profile_requests.pop(user_id, None)
            return {}
        task = asyncio.create_task(_fetch())
        self._profile_requests[user_id] = task
        return await task
    
    async def close(self):
        await self.stop_sync()
        if self.client: await self.client.close(); self.client = None
