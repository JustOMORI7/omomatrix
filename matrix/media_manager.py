"""
Media manager for downloading and caching general media (images) from Matrix.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Set
from io import BytesIO

import aiohttp
from PIL import Image

from config import config

logger = logging.getLogger(__name__)


class MediaManager:
    """Manages downloading and caching of Matrix media."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize media manager.
        
        Args:
            cache_dir: Directory for caching media. Defaults to config.cache_dir / "media".
        """
        self.cache_dir = cache_dir or (config.cache_dir / "media")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Parallel download control
        self._download_semaphore = asyncio.Semaphore(10)
        self._active_downloads: Dict[Path, asyncio.Task] = {}
        self._path_cache: Dict[str, Path] = {}
        self._failure_cache: Set[str] = set()
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    def _get_cache_path(self, mxc_url: str, width: Optional[int] = None, height: Optional[int] = None) -> Path:
        """Get cache file path for an MXC URL and dimensions."""
        key = f"{mxc_url}_{width}_{height}"
        url_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.png"
    
    async def get_media(
        self,
        homeserver: str,
        mxc_url: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        access_token: Optional[str] = None
    ) -> Optional[Path]:
        """Get media file path, downloading if necessary.
        
        Args:
            homeserver: Matrix homeserver URL
            mxc_url: Matrix content URL (mxc://...)
            width: Optional width for thumbnail
            height: Optional height for thumbnail
            access_token: Matrix access token for authenticated media
            
        Returns:
            Path to media file, or None if failed
        """
        if not mxc_url or not mxc_url.startswith("mxc://"):
            return None
            
        cache_key = f"{mxc_url}_{width}_{height}"
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]
            
        if mxc_url in self._failure_cache:
            return None
            
        cache_path = self._get_cache_path(mxc_url, width, height)
        if cache_path.exists():
            self._path_cache[cache_key] = cache_path
            return cache_path
            
        if cache_path in self._active_downloads:
            return await self._active_downloads[cache_path]

        async def _download():
            try:
                async with self._download_semaphore:
                    await self._ensure_session()
                    
                    base_url = homeserver
                    if not base_url.startswith("http"):
                        base_url = f"https://{base_url}"
                    
                    mxc_base = mxc_url[6:]
                    if "/" not in mxc_base:
                        return None
                        
                    server, media_id = mxc_base.split("/", 1)
                    
                    # Endpoints
                    media_prefix = "/_matrix/client/v1/media" if access_token else "/_matrix/media/v3"
                    
                    if width and height:
                        http_url = f"{base_url.rstrip('/')}{media_prefix}/thumbnail/{server}/{media_id}?width={width}&height={height}&method=scale"
                    else:
                        http_url = f"{base_url.rstrip('/')}{media_prefix}/download/{server}/{media_id}"
                    
                    headers = {}
                    if access_token:
                        headers["Authorization"] = f"Bearer {access_token}"
                        
                    logger.debug(f"Downloading media {mxc_url} from {http_url}")
                    async with self.session.get(http_url, headers=headers, timeout=30) as response:
                        if response.status == 200:
                            data = await response.read()
                            
                            # Save and process image
                            image = Image.open(BytesIO(data))
                            
                            # Enforce reasonable limits if it was a full download
                            if not width or not height:
                                max_size = (1200, 1200)
                                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                            
                            image.save(cache_path, "PNG")
                            self._path_cache[cache_key] = cache_path
                            return cache_path
                        else:
                            logger.warning(f"Failed to download media {mxc_url}: {response.status}")
                            self._failure_cache.add(mxc_url)
                            return None
            except Exception as e:
                logger.error(f"Error downloading media {mxc_url}: {e}")
                return None
            finally:
                self._active_downloads.pop(cache_path, None)

        task = asyncio.create_task(_download())
        self._active_downloads[cache_path] = task
        return await task

    async def close(self):
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()
