"""Individual data collectors for different event types."""

import time
import psutil
from pynput import keyboard, mouse
from typing import Optional, Callable
import threading

class KeystrokeCollector:
    """Collects keystroke events (timing, patterns, AND content for local analysis)."""
    
    def __init__(self, callback: Callable, active_window_getter: Callable, log_content: bool = True):
        """
        Initialize keystroke collector.
        
        Args:
            callback: Function to call with (timestamp, key_name, key_code, is_press, duration_ms, active_window, key_content)
            active_window_getter: Function that returns current active window name
            log_content: Whether to log actual key content (True for local analysis)
        """
        self.callback = callback
        self.active_window_getter = active_window_getter
        self.log_content = log_content
        self.key_press_times = {}  # Track when keys were pressed
        self.last_key_time = time.time()
        self.keystroke_buffer = []  # Track typing patterns
        self.listener: Optional[keyboard.Listener] = None
        self.running = False
    
    def _on_press(self, key):
        """Handle key press event."""
        try:
            timestamp = time.time()
            key_name = str(key).replace("'", "")
            key_code = key.value.vk if hasattr(key, 'value') and hasattr(key.value, 'vk') else None
            active_window = self.active_window_getter()
            
            # Calculate time since last key
            time_since_last = (timestamp - self.last_key_time) * 1000  # in ms
            self.last_key_time = timestamp
            
            # Store press time
            self.key_press_times[key] = timestamp
            
            # Get key content if logging content
            key_content = None
            if self.log_content:
                try:
                    if hasattr(key, 'char') and key.char:
                        key_content = key.char
                    elif key_name.startswith('Key.'):
                        key_content = key_name.replace('Key.', '').lower()
                    else:
                        key_content = key_name
                except:
                    key_content = key_name
            
            # Track typing patterns
            if time_since_last < 1000:  # Only track if within 1 second
                self.keystroke_buffer.append(time_since_last)
                if len(self.keystroke_buffer) > 20:
                    self.keystroke_buffer.pop(0)
            
            self.callback(
                timestamp=timestamp,
                key_name=key_name,
                key_code=key_code,
                is_press=True,
                duration_ms=0.0,
                active_window=active_window,
                key_content=key_content,
                time_since_last_key_ms=time_since_last,
                typing_speed_wpm=self._calculate_typing_speed()
            )
        except Exception as e:
            print(f"Error in keystroke press handler: {e}")
    
    def _calculate_typing_speed(self):
        """Calculate typing speed in WPM."""
        if len(self.keystroke_buffer) < 5:
            return 0
        avg_time = sum(self.keystroke_buffer) / len(self.keystroke_buffer)
        if avg_time == 0:
            return 0
        # Average character time to WPM (assuming 5 chars per word)
        chars_per_min = (1000 / avg_time) * 60
        return int(chars_per_min / 5)
    
    def _on_release(self, key):
        """Handle key release event."""
        try:
            timestamp = time.time()
            key_name = str(key).replace("'", "")
            key_code = key.value.vk if hasattr(key, 'value') and hasattr(key.value, 'vk') else None
            active_window = self.active_window_getter()
            
            # Calculate duration
            duration_ms = 0.0
            if key in self.key_press_times:
                duration_ms = (timestamp - self.key_press_times[key]) * 1000
                del self.key_press_times[key]
            
            # Get key content if logging content
            key_content = None
            if self.log_content:
                try:
                    if hasattr(key, 'char') and key.char:
                        key_content = key.char
                    elif key_name.startswith('Key.'):
                        key_content = key_name.replace('Key.', '').lower()
                    else:
                        key_content = key_name
                except:
                    key_content = key_name
            
            self.callback(
                timestamp=timestamp,
                key_name=key_name,
                key_code=key_code,
                is_press=False,
                duration_ms=duration_ms,
                active_window=active_window,
                key_content=key_content,
                typing_speed_wpm=self._calculate_typing_speed()
            )
        except Exception as e:
            print(f"Error in keystroke release handler: {e}")
    
    def start(self):
        """Start collecting keystrokes."""
        if not self.running:
            self.running = True
            self.listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self.listener.start()
    
    def stop(self):
        """Stop collecting keystrokes."""
        self.running = False
        if self.listener:
            self.listener.stop()
            self.listener = None


class MouseCollector:
    """Collects mouse events (clicks, movement, scrolling)."""
    
    def __init__(self, callback: Callable, active_window_getter: Callable):
        """
        Initialize mouse collector.
        
        Args:
            callback: Function to call with (timestamp, event_type, x, y, button, scroll_delta_x, scroll_delta_y, active_window)
            active_window_getter: Function that returns current active window name
        """
        self.callback = callback
        self.active_window_getter = active_window_getter
        self.listener: Optional[mouse.Listener] = None
        self.running = False
        self.last_move_time = time.time()
        self.move_threshold = 0.1  # Only log moves every 100ms to avoid spam
    
    def _on_move(self, x, y):
        """Handle mouse movement (throttled)."""
        current_time = time.time()
        if current_time - self.last_move_time < self.move_threshold:
            return
        self.last_move_time = current_time
        
        try:
            timestamp = time.time()
            active_window = self.active_window_getter()
            self.callback(
                timestamp=timestamp,
                event_type='move',
                x=x,
                y=y,
                button=None,
                scroll_delta_x=0,
                scroll_delta_y=0,
                active_window=active_window
            )
        except Exception as e:
            print(f"Error in mouse move handler: {e}")
    
    def _on_click(self, x, y, button, pressed):
        """Handle mouse click."""
        try:
            timestamp = time.time()
            active_window = self.active_window_getter()
            event_type = 'click_press' if pressed else 'click_release'
            button_name = str(button).replace('Button.', '')
            
            self.callback(
                timestamp=timestamp,
                event_type=event_type,
                x=x,
                y=y,
                button=button_name if pressed else None,
                scroll_delta_x=0,
                scroll_delta_y=0,
                active_window=active_window
            )
        except Exception as e:
            print(f"Error in mouse click handler: {e}")
    
    def _on_scroll(self, x, y, dx, dy):
        """Handle mouse scroll."""
        try:
            timestamp = time.time()
            active_window = self.active_window_getter()
            self.callback(
                timestamp=timestamp,
                event_type='scroll',
                x=x,
                y=y,
                button=None,
                scroll_delta_x=dx,
                scroll_delta_y=dy,
                active_window=active_window
            )
        except Exception as e:
            print(f"Error in mouse scroll handler: {e}")
    
    def start(self):
        """Start collecting mouse events."""
        if not self.running:
            self.running = True
            self.listener = mouse.Listener(
                on_move=self._on_move,
                on_click=self._on_click,
                on_scroll=self._on_scroll
            )
            self.listener.start()
    
    def stop(self):
        """Stop collecting mouse events."""
        self.running = False
        if self.listener:
            self.listener.stop()
            self.listener = None


class ApplicationCollector:
    """Collects application/window switching events."""
    
    def __init__(self, callback: Callable, sample_rate_ms: int = 1000):
        """
        Initialize application collector.
        
        Args:
            callback: Function to call with (timestamp, event_type, application_name, window_title, process_id, duration_seconds)
            sample_rate_ms: How often to check for application changes (in milliseconds)
        """
        self.callback = callback
        self.sample_rate_ms = sample_rate_ms / 1000.0
        self.current_app = None
        self.current_window = None
        self.app_start_time = time.time()
        self.running = False
        self.thread: Optional[threading.Thread] = None
    
    def _get_active_window(self) -> tuple:
        """Get current active window (app name, window title, PID)."""
        try:
            # This is platform-specific. For Linux, we'll use a simple approach
            # You may need to install additional packages like xdotool or wmctrl
            import subprocess
            try:
                result = subprocess.run(
                    ['xdotool', 'getactivewindow', 'getwindowname'],
                    capture_output=True,
                    text=True,
                    timeout=0.1
                )
                window_title = result.stdout.strip()
            except:
                window_title = "Unknown"
            
            # Get active process
            try:
                # Try to get foreground process (Linux-specific)
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name']:
                            # This is a simplified version - may need refinement
                            return (proc.info['name'], window_title, proc.info['pid'])
                    except:
                        continue
            except:
                pass
            
            return ("Unknown", window_title, 0)
        except Exception as e:
            return ("Unknown", "Unknown", 0)
    
    def _monitor_loop(self):
        """Background thread to monitor application changes."""
        while self.running:
            try:
                app_name, window_title, pid = self._get_active_window()
                
                # Check if application changed
                if app_name != self.current_app or window_title != self.current_window:
                    # Log the previous app's duration
                    if self.current_app:
                        duration = time.time() - self.app_start_time
                        self.callback(
                            timestamp=self.app_start_time,
                            event_type='switch',
                            application_name=self.current_app,
                            window_title=self.current_window,
                            process_id=0,  # Will be updated
                            duration_seconds=duration
                        )
                    
                    # Update current app
                    self.current_app = app_name
                    self.current_window = window_title
                    self.app_start_time = time.time()
                    
                    # Log new app
                    self.callback(
                        timestamp=time.time(),
                        event_type='switch',
                        application_name=app_name,
                        window_title=window_title,
                        process_id=pid,
                        duration_seconds=0.0
                    )
                
                time.sleep(self.sample_rate_ms)
            except Exception as e:
                print(f"Error in application monitor: {e}")
                time.sleep(self.sample_rate_ms)
    
    def start(self):
        """Start collecting application events."""
        if not self.running:
            self.running = True
            self.app_start_time = time.time()
            self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.thread.start()
    
    def stop(self):
        """Stop collecting application events."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)


class FileCollector:
    """Collects file operation events (create, edit, delete, save)."""
    
    def __init__(self, callback: Callable, watch_directories: list):
        """
        Initialize file collector.
        
        Args:
            callback: Function to call with (timestamp, operation_type, file_path, file_extension, file_size_bytes)
            watch_directories: List of directories to watch for file changes
        """
        self.callback = callback
        self.watch_directories = watch_directories
        self.observer = None
        self.running = False
    
    def start(self):
        """Start collecting file events."""
        # File watching will be implemented with watchdog
        # For now, this is a placeholder
        # TODO: Implement with watchdog.FileSystemEventHandler
        pass
    
    def stop(self):
        """Stop collecting file events."""
        if self.observer:
            self.observer.stop()
            self.observer = None
        self.running = False


