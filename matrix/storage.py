"""
Credential and session storage for OMOMatrix.

Manages storing and retrieving Matrix credentials, device IDs, and access tokens.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

from config import config


class CredentialStorage:
    """Handles secure storage of Matrix credentials and session data."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize credential storage.
        
        Args:
            db_path: Path to SQLite database. Defaults to config.database_path.
        """
        self.db_path = db_path or config.database_path
        self._init_database()
    
    def _init_database(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Create credentials table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                homeserver TEXT NOT NULL,
                user_id TEXT NOT NULL,
                access_token TEXT NOT NULL,
                device_id TEXT NOT NULL,
                data TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_credentials(
        self,
        homeserver: str,
        user_id: str,
        access_token: str,
        device_id: str,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """Save Matrix credentials.
        
        Args:
            homeserver: Matrix homeserver URL
            user_id: Full Matrix user ID (e.g., @user:matrix.org)
            access_token: Access token from login
            device_id: Device ID from login
            extra_data: Additional data to store as JSON
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        data_json = json.dumps(extra_data) if extra_data else None
        
        cursor.execute("""
            INSERT OR REPLACE INTO credentials (id, homeserver, user_id, access_token, device_id, data)
            VALUES (1, ?, ?, ?, ?, ?)
        """, (homeserver, user_id, access_token, device_id, data_json))
        
        conn.commit()
        conn.close()
    
    def load_credentials(self) -> Optional[Dict[str, Any]]:
        """Load saved credentials.
        
        Returns:
            Dictionary with credentials or None if not found
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT homeserver, user_id, access_token, device_id, data
            FROM credentials
            WHERE id = 1
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        homeserver, user_id, access_token, device_id, data_json = row
        
        extra_data = json.loads(data_json) if data_json else {}
        
        return {
            'homeserver': homeserver,
            'user_id': user_id,
            'access_token': access_token,
            'device_id': device_id,
            **extra_data
        }
    
    def clear_credentials(self):
        """Clear all stored credentials."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM credentials WHERE id = 1")
        
        conn.commit()
        conn.close()
    
    def has_credentials(self) -> bool:
        """Check if credentials are stored.
        
        Returns:
            True if credentials exist, False otherwise
        """
        return self.load_credentials() is not None
