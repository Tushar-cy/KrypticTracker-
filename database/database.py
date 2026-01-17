"""Database manager with encryption support."""

import sqlite3
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class DatabaseManager:
    """Manages encrypted SQLite database operations."""
    
    def __init__(self, db_path: str, encrypted: bool = True, password: Optional[str] = None):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
            encrypted: Whether to use encryption
            password: Password for encryption (if None, uses default or generates key)
        """
        self.db_path = Path(db_path)
        self.encrypted = encrypted
        self.connection: Optional[sqlite3.Connection] = None
        
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Encryption setup
        if encrypted:
            self._setup_encryption(password)
        else:
            self.cipher = None
    
    def _setup_encryption(self, password: Optional[str] = None):
        """Set up encryption key."""
        key_file = self.db_path.parent / ".encryption_key"
        
        if password:
            # Derive key from password
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'kryptictrack_salt',  # In production, use random salt
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        elif key_file.exists():
            # Load existing key
            with open(key_file, 'rb') as f:
                key = f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            # Make key file readable only by owner
            os.chmod(key_file, 0o600)
        
        self.cipher = Fernet(key)
    
    def connect(self):
        """Establish database connection."""
        # Check if connection exists and is still open
        if self.connection is None:
            self.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self.connection.row_factory = sqlite3.Row
        else:
            # Check if connection is closed and reconnect if needed
            try:
                self.connection.execute("SELECT 1")
            except (sqlite3.ProgrammingError, sqlite3.OperationalError):
                # Connection is closed, reconnect
                self.connection = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False
                )
                self.connection.row_factory = sqlite3.Row
        return self.connection
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def _encrypt_value(self, value: Any) -> bytes:
        """Encrypt a value for storage."""
        if not self.encrypted or self.cipher is None:
            return value
        if isinstance(value, str):
            return self.cipher.encrypt(value.encode())
        elif isinstance(value, (dict, list)):
            return self.cipher.encrypt(json.dumps(value).encode())
        else:
            return self.cipher.encrypt(str(value).encode())
    
    def _decrypt_value(self, value: bytes) -> Any:
        """Decrypt a value from storage."""
        if not self.encrypted or self.cipher is None:
            return value
        try:
            decrypted = self.cipher.decrypt(value)
            # Try to decode as JSON first, then as string
            try:
                return json.loads(decrypted.decode())
            except:
                return decrypted.decode()
        except:
            return value
    
    def insert_keystroke(self, timestamp: float, key_name: str, key_code: int,
                        is_press: bool, duration_ms: float, active_window: str,
                        session_id: str):
        """Insert keystroke event."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO keystrokes 
            (timestamp, key_name, key_code, is_press, duration_ms, active_window, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, key_name, key_code, is_press, duration_ms, active_window, session_id))
        conn.commit()
    
    def insert_mouse_event(self, timestamp: float, event_type: str, x: int, y: int,
                          button: Optional[str] = None, scroll_delta_x: float = 0,
                          scroll_delta_y: float = 0, active_window: str = "",
                          session_id: str = ""):
        """Insert mouse event."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mouse_events
            (timestamp, event_type, x, y, button, scroll_delta_x, scroll_delta_y, active_window, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, event_type, x, y, button, scroll_delta_x, scroll_delta_y, active_window, session_id))
        conn.commit()
    
    def insert_application_event(self, timestamp: float, event_type: str,
                                application_name: str, window_title: str,
                                process_id: int, duration_seconds: float,
                                session_id: str):
        """Insert application/window event."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO application_events
            (timestamp, event_type, application_name, window_title, process_id, duration_seconds, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, event_type, application_name, window_title, process_id, duration_seconds, session_id))
        conn.commit()
    
    def insert_file_operation(self, timestamp: float, operation_type: str,
                             file_path: str, file_extension: str,
                             file_size_bytes: int, session_id: str):
        """Insert file operation event."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO file_operations
            (timestamp, operation_type, file_path, file_extension, file_size_bytes, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (timestamp, operation_type, file_path, file_extension, file_size_bytes, session_id))
        conn.commit()
    
    def insert_context_switch(self, timestamp: float, from_context: str,
                             to_context: str, trigger_event: str, session_id: str):
        """Insert context switch event."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO context_switches
            (timestamp, from_context, to_context, trigger_event, session_id)
            VALUES (?, ?, ?, ?, ?)
        """, (timestamp, from_context, to_context, trigger_event, session_id))
        conn.commit()
    
    def get_recent_events(self, table: str, limit: int = 100):
        """Get recent events from a table."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table} ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

