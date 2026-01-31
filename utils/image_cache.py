"""
Simple image cache for Matrix media.
"""
import os
import hashlib
from pathlib import Path

class ImageCache:
    """
    Manages downloaded Matrix images.
    """
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            # Use user's temp directory
            cache_dir = Path.home() / ".omomatrix" / "image_cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_path(self, mxc_url: str, data: bytes = None) -> Path:
        """
        Get the local file path for a given mxc:// URL.
        If data is None, it tries to find an existing file on disk.
        """
        url_hash = hashlib.md5(mxc_url.encode()).hexdigest()
        
        # If no data is provided, try to find an existing file with any common extension
        if data is None:
            for f in self.cache_dir.glob(f"{url_hash}.*"):
                return f
        
        # Determine extension for saving or if file not found
        ext = ".jpg" # Default
        
        if data:
            # Simple magic byte check
            if data.startswith(b'\x89PNG\r\n\x1a\n'):
                ext = ".png"
            elif data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
                ext = ".gif"
            elif data.startswith(b'\xff\xd8'):
                ext = ".jpg"
            elif data.startswith(b'RIFF') and b'WEBP' in data[:12]:
                ext = ".webp"
        
        if ext == ".jpg" and "/" in mxc_url:
            media_id = mxc_url.split("/")[-1]
            if "." in media_id:
                potential_ext = "." + media_id.split(".")[-1].lower()
                if potential_ext in [".png", ".gif", ".webp", ".jpg", ".jpeg"]:
                    ext = potential_ext
        
        return self.cache_dir / f"{url_hash}{ext}"
    
    def is_cached(self, mxc_url: str) -> bool:
        """
        Check if an image is already cached.
        Note: This is an approximation since we don't know the extension 100% 
        without checking multiple possibilities if it's not data-driven.
        """
        # Search for any file with this hash in the cache dir
        url_hash = hashlib.md5(mxc_url.encode()).hexdigest()
        for f in self.cache_dir.glob(f"{url_hash}.*"):
            return True
        return False

    def save_image(self, mxc_url: str, data: bytes):
        """
        Save image data to cache.
        """
        path = self.get_cache_path(mxc_url, data)
        path.write_bytes(data)
        return path
