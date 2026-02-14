"""
Avatar manager for downloading and caching user profile pictures.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional
from io import BytesIO

import aiohttp
from PIL import Image

from config import config

logger = logging.getLogger(__name__)


class AvatarManager:
    """Manages downloading and caching of user avatars."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize avatar manager.
        
        Args:
            cache_dir: Directory for caching avatars. Defaults to config.avatar_cache_dir.
        """
        self.cache_dir = cache_dir or config.avatar_cache_dir
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Performance optimizations
        self._download_semaphore = asyncio.Semaphore(30)
        self._active_downloads: Dict[Path, asyncio.Task] = {}
        self._path_cache: Dict[str, Path] = {}
        self._failure_cache: Set[str] = set()
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    def _get_cache_path(self, mxc_url: str, size: int = 64) -> Path:
        """Get cache file path for an MXC URL.
        
        Args:
            mxc_url: Matrix content URL (mxc://...)
            size: Avatar size in pixels
            
        Returns:
            Path to cached file
        """
        # Create hash from MXC URL and size
        url_hash = hashlib.md5(f"{mxc_url}_{size}".encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.png"
    
    async def get_avatar(
        self,
        homeserver: str,
        mxc_url: str,
        size: int = 64,
        access_token: Optional[str] = None
    ) -> Optional[Path]:
        """Get avatar image, downloading if necessary.
        
        Args:
            homeserver: Matrix homeserver URL
            mxc_url: Matrix content URL (mxc://server/media_id)
            size: Desired avatar size in pixels
            access_token: Optional Matrix access token for authenticated media
            
        Returns:
            Path to avatar image file, or None if failed
        """
        if not mxc_url or not mxc_url.startswith("mxc://"):
            return None
        
        # Check in-memory path cache first
        cache_key = f"{mxc_url}_{size}"
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]
            
        # Check negative cache
        if mxc_url in self._failure_cache:
            return None
        
        # Check disk cache
        cache_path = self._get_cache_path(mxc_url, size)
        if cache_path.exists():
            self._path_cache[cache_key] = cache_path
            return cache_path
        
        # Download avatar
        if cache_path in self._active_downloads:
            try:
                return await self._active_downloads[cache_path]
            except Exception:
                return None

        async def _download():
            try:
                async with self._download_semaphore:
                    await self._ensure_session()
                    
                    # Ensure homeserver has a schema
                    base_url = homeserver
                    if not base_url.startswith("http"):
                        base_url = f"https://{base_url}"
                    
                    # Convert MXC URL to HTTP URL
                    mxc_base = mxc_url[6:]
                    if "/" not in mxc_base:
                        logger.error(f"Invalid MXC URL (missing slash): {mxc_url}")
                        return None
                        
                    server, media_id = mxc_base.split("/", 1)
                    
                    # Modern authenticated media endpoints use /_matrix/client/v1/media/
                    # Fallback to /_matrix/media/v3/ for unauthenticated or older servers
                    media_prefix = "/_matrix/client/v1/media" if access_token else "/_matrix/media/v3"
                    
                    thumbnail_url = f"{base_url.rstrip('/')}{media_prefix}/thumbnail/{server}/{media_id}?width={size}&height={size}&method=crop"
                    download_url = f"{base_url.rstrip('/')}{media_prefix}/download/{server}/{media_id}"
                    
                    headers = {}
                    if access_token:
                        headers["Authorization"] = f"Bearer {access_token}"
                    
                    image_data = None
                    
                    # Strategy: Try thumbnail first, then fallback to full download if thumbnail fails
                    for label, http_url in [("thumbnail", thumbnail_url), ("full", download_url)]:
                        try:
                            logger.debug(f"Attempting {label} download for {mxc_url} from {http_url}")
                            async with self.session.get(http_url, headers=headers, timeout=15) as response:
                                if response.status == 200:
                                    image_data = await response.read()
                                    logger.info(f"Successfully downloaded {label} ({len(image_data)} bytes) for {mxc_url}")
                                    break
                                elif response.status == 404:
                                    logger.warning(f"{label} download returned 404 for {mxc_url}")
                                    continue
                                else:
                                    logger.warning(f"Failed to download {label} for {mxc_url}: {response.status}")
                                    if label == "thumbnail": continue # Try full download
                                    return None
                        except Exception as e:
                            logger.error(f"Error during {label} download for {mxc_url}: {e}")
                            if label == "thumbnail": continue
                            return None
                    
                    if not image_data:
                        logger.warning(f"All download attempts failed for {mxc_url}")
                        self._failure_cache.add(mxc_url)
                        return None
                    
                    # Process and resize image
                    logger.debug(f"Processing image data for {mxc_url}")
                    image = Image.open(BytesIO(image_data))
                    
                    # Convert to RGB if needed (remove alpha channel)
                    if image.mode in ('RGBA', 'LA', 'P'):
                        logger.debug(f"Converting image mode {image.mode} to RGB")
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        if image.mode == 'P':
                            image = image.convert('RGBA')
                        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                        image = background
                    
                    # Resize to requested size
                    image = image.resize((size, size), Image.Resampling.LANCZOS)
                    
                    # Save to cache
                    image.save(cache_path, 'PNG')
                    logger.info(f"Successfully saved avatar to cache: {cache_path}")
                    
                    self._path_cache[cache_key] = cache_path
                    return cache_path
            except Exception as e:
                logger.error(f"Error processing/downloading avatar {mxc_url}: {e}", exc_info=True)
                return None
            finally:
                self._active_downloads.pop(cache_path, None)

        task = asyncio.create_task(_download())
        self._active_downloads[cache_path] = task
        return await task
    
    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def clear_cache(self):
        """Clear all cached avatars."""
        for file in self.cache_dir.glob("*.png"):
            try:
                file.unlink()
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")
