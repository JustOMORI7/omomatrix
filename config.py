"""
Configuration management for OMOMatrix.

Handles application directories and settings following XDG Base Directory spec.
"""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Application configuration manager."""
    
    APP_NAME = "omomatrix"
    APP_VERSION = "0.1.0"
    
    def __init__(self):
        """Initialize configuration paths."""
        self._config_dir: Optional[Path] = None
        self._data_dir: Optional[Path] = None
        self._cache_dir: Optional[Path] = None
    
    @property
    def config_dir(self) -> Path:
        """Get configuration directory path.
        
        Returns:
            Path to config directory (e.g., ~/.config/omomatrix)
        """
        if self._config_dir is None:
            xdg_config = os.getenv("XDG_CONFIG_HOME")
            if xdg_config:
                base = Path(xdg_config)
            else:
                base = Path.home() / ".config"
            
            self._config_dir = base / self.APP_NAME
            self._config_dir.mkdir(parents=True, exist_ok=True)
        
        return self._config_dir
    
    @property
    def data_dir(self) -> Path:
        """Get data directory path.
        
        Returns:
            Path to data directory (e.g., ~/.local/share/omomatrix)
        """
        if self._data_dir is None:
            xdg_data = os.getenv("XDG_DATA_HOME")
            if xdg_data:
                base = Path(xdg_data)
            else:
                base = Path.home() / ".local" / "share"
            
            self._data_dir = base / self.APP_NAME
            self._data_dir.mkdir(parents=True, exist_ok=True)
        
        return self._data_dir
    
    @property
    def cache_dir(self) -> Path:
        """Get cache directory path.
        
        Returns:
            Path to cache directory (e.g., ~/.cache/omomatrix)
        """
        if self._cache_dir is None:
            xdg_cache = os.getenv("XDG_CACHE_HOME")
            if xdg_cache:
                base = Path(xdg_cache)
            else:
                base = Path.home() / ".cache"
            
            self._cache_dir = base / self.APP_NAME
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        return self._cache_dir
    
    @property
    def database_path(self) -> Path:
        """Get database file path.
        
        Returns:
            Path to SQLite database file
        """
        return self.data_dir / "omomatrix.db"
    
    @property
    def avatar_cache_dir(self) -> Path:
        """Get avatar cache directory.
        
        Returns:
            Path to avatar cache directory
        """
        avatar_dir = self.cache_dir / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        return avatar_dir
    
    @property
    def store_path(self) -> Path:
        """Get matrix-nio store path for E2EE keys.
        
        Returns:
            Path to matrix-nio store directory
        """
        store_path = self.data_dir / "store"
        store_path.mkdir(parents=True, exist_ok=True)
        return store_path


# Global configuration instance
config = Config()
