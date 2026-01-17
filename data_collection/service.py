"""Main data collection service that orchestrates all collectors."""

import time
import signal
import sys
from pathlib import Path
from typing import Optional

from database import DatabaseManager
from database.schema import create_tables
from .collectors import (
    KeystrokeCollector,
    MouseCollector,
    ApplicationCollector,
    FileCollector
)
from utils.helpers import get_active_window, generate_session_id, load_config


class DataCollectionService:
    """Main service that coordinates all data collectors."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize data collection service."""
        self.config = load_config(config_path)
        self.db_config = self.config['database']
        self.collection_config = self.config['data_collection']
        
        # Initialize database
        self.db = DatabaseManager(
            db_path=self.db_config['path'],
            encrypted=self.db_config['encrypted']
        )
        self.db.connect()
        create_tables(self.db.connection)
        
        # Generate session ID
        self.session_id = generate_session_id()
        self.start_time = time.time()
        
        # Initialize collectors
        self.keystroke_collector: Optional[KeystrokeCollector] = None
        self.mouse_collector: Optional[MouseCollector] = None
        self.app_collector: Optional[ApplicationCollector] = None
        self.file_collector: Optional[FileCollector] = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.running = False
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print("\n🛑 Shutting down data collection service...")
        self.stop()
        sys.exit(0)
    
    def _keystroke_callback(self, timestamp, key_name, key_code, is_press, duration_ms, active_window, 
                           key_content=None, time_since_last_key_ms=0, typing_speed_wpm=0):
        """Callback for keystroke events."""
        if self.collection_config['log_keystrokes']:
            # Also log to unified actions table for richer data
            context = {
                'key_name': key_name,
                'key_code': key_code,
                'is_press': is_press,
                'duration_ms': duration_ms,
                'active_window': active_window,
                'key_content': key_content,  # Actual key content for local analysis
                'time_since_last_key_ms': time_since_last_key_ms,
                'typing_speed_wpm': typing_speed_wpm
            }
            
            # Log to unified actions table
            import json
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                VALUES (?, ?, ?, ?, ?)
            """, (timestamp, 'system', 'keystroke', json.dumps(context), self.session_id))
            conn.commit()
            
            # Also log to legacy table for compatibility
            self.db.insert_keystroke(
                timestamp=timestamp,
                key_name=key_name,
                key_code=key_code,
                is_press=is_press,
                duration_ms=duration_ms,
                active_window=active_window,
                session_id=self.session_id
            )
    
    def _mouse_callback(self, timestamp, event_type, x, y, button, scroll_delta_x, scroll_delta_y, active_window):
        """Callback for mouse events."""
        if self.collection_config['log_mouse']:
            # Also log to unified actions table
            context = {
                'event_type': event_type,
                'x': x,
                'y': y,
                'button': button,
                'scroll_delta_x': scroll_delta_x,
                'scroll_delta_y': scroll_delta_y,
                'active_window': active_window
            }
            
            import json
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                VALUES (?, ?, ?, ?, ?)
            """, (timestamp, 'system', f'mouse_{event_type}', json.dumps(context), self.session_id))
            conn.commit()
            
            # Also log to legacy table
            self.db.insert_mouse_event(
                timestamp=timestamp,
                event_type=event_type,
                x=x,
                y=y,
                button=button,
                scroll_delta_x=scroll_delta_x,
                scroll_delta_y=scroll_delta_y,
                active_window=active_window,
                session_id=self.session_id
            )
    
    def _app_callback(self, timestamp, event_type, application_name, window_title, process_id, duration_seconds):
        """Callback for application events."""
        if self.collection_config['log_applications']:
            self.db.insert_application_event(
                timestamp=timestamp,
                event_type=event_type,
                application_name=application_name,
                window_title=window_title,
                process_id=process_id,
                duration_seconds=duration_seconds,
                session_id=self.session_id
            )
    
    def _file_callback(self, timestamp, operation_type, file_path, file_extension, file_size_bytes):
        """Callback for file operations."""
        if self.collection_config['log_files']:
            self.db.insert_file_operation(
                timestamp=timestamp,
                operation_type=operation_type,
                file_path=file_path,
                file_extension=file_extension,
                file_size_bytes=file_size_bytes,
                session_id=self.session_id
            )
    
    def start(self):
        """Start all data collectors."""
        if self.running:
            print("⚠️  Service is already running")
            return
        
        print("🚀 Starting KrypticTrack Data Collection Service...")
        print(f"📊 Session ID: {self.session_id}")
        print(f"💾 Database: {self.db_config['path']}")
        print(f"🔒 Encrypted: {self.db_config['encrypted']}")
        print("\n📝 Collecting:")
        print(f"  - Keystrokes: {self.collection_config['log_keystrokes']}")
        print(f"  - Mouse: {self.collection_config['log_mouse']}")
        print(f"  - Applications: {self.collection_config['log_applications']}")
        print(f"  - Files: {self.collection_config['log_files']}")
        print(f"  - Context Switches: {self.collection_config['log_context_switches']}")
        print("\n✅ Service started! Press Ctrl+C to stop.\n")
        
        self.running = True
        
        # Start collectors based on config
        if self.collection_config['log_keystrokes']:
            # Log content for local analysis (privacy: all local)
            self.keystroke_collector = KeystrokeCollector(
                callback=self._keystroke_callback,
                active_window_getter=get_active_window,
                log_content=True  # Log actual key content for rich behavioral data
            )
            self.keystroke_collector.start()
            print("✅ Keystroke collector started (logging content for local analysis)")
        
        if self.collection_config['log_mouse']:
            self.mouse_collector = MouseCollector(
                callback=self._mouse_callback,
                active_window_getter=get_active_window
            )
            self.mouse_collector.start()
            print("✅ Mouse collector started")
        
        if self.collection_config['log_applications']:
            sample_rate = self.collection_config.get('sample_rate_ms', 1000)
            self.app_collector = ApplicationCollector(
                callback=self._app_callback,
                sample_rate_ms=sample_rate
            )
            self.app_collector.start()
            print("✅ Application collector started")
        
        if self.collection_config['log_files']:
            # TODO: Get watch directories from config
            watch_dirs = [str(Path.home())]  # Default: watch home directory
            self.file_collector = FileCollector(
                callback=self._file_callback,
                watch_directories=watch_dirs
            )
            self.file_collector.start()
            print("✅ File collector started")
        
        # Keep service running
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop all data collectors."""
        if not self.running:
            return
        
        print("\n🛑 Stopping collectors...")
        self.running = False
        
        if self.keystroke_collector:
            self.keystroke_collector.stop()
            print("✅ Keystroke collector stopped")
        
        if self.mouse_collector:
            self.mouse_collector.stop()
            print("✅ Mouse collector stopped")
        
        if self.app_collector:
            self.app_collector.stop()
            print("✅ Application collector stopped")
        
        if self.file_collector:
            self.file_collector.stop()
            print("✅ File collector stopped")
        
        # Close database
        self.db.close()
        print("✅ Database connection closed")
        
        duration = time.time() - self.start_time
        print(f"\n📊 Session Summary:")
        print(f"  - Duration: {duration/60:.1f} minutes")
        print(f"  - Session ID: {self.session_id}")
        print("✅ Service stopped successfully")


if __name__ == "__main__":
    service = DataCollectionService()
    service.start()

