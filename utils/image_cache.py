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
    
    def get_cache_path(self, mxc_url: str) -> Path:
        """
        Get the local file path for a given mxc:// URL.
        """
        # Create a hash of the mxc URL to use as filename
        # This ensures no invalid path characters
        url_hash = hashlib.md5(mxc_url.encode()).hexdigest()
        
        # Try to extract file extension from URL
        ext = ".jpg"  # Default
        if "/" in mxc_url:
            # Get the media_id part (after last /)
            media_id = mxc_url.split("/")[-1]
            if "." in media_id:
                ext = "." + media_id.split(".")[-1]
        
        return self.cache_dir / f"{url_hash}{ext}"
    
    def is_cached(self, mxc_url: str) -> bool:
        """
        Check if an image is already cached.
        """
        return self.get_cache_path(mxc_url).exists()
    
    def save_image(self, mxc_url: str, data: bytes):
        """
        Save image data to cache.
        """
        path = self.get_cache_path(mxc_url)
        path.write_bytes(data)
        return path
