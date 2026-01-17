"""
System Logger Daemon
Tracks OS-level activity: app switches, window focus, mouse/keyboard activity, idle detection
"""

import time
import json
import requests
import psutil
from datetime import datetime
from typing import Dict, Optional
import platform

# Platform-specific imports
if platform.system() == 'Linux':
    try:
        import Xlib.display
        from Xlib import X
        HAS_X11 = True
    except ImportError:
        HAS_X11 = False
        print("Warning: X11 not available, limited functionality")
elif platform.system() == 'Windows':
    try:
        import win32gui
        import win32process
        HAS_WIN32 = True
    except ImportError:
        HAS_WIN32 = False
        print("Warning: win32gui not available, limited functionality")
else:
    HAS_X11 = False
    HAS_WIN32 = False


class SystemLogger:
    """Tracks system-level activity with comprehensive app and window tracking."""
    
    def __init__(self, api_url: str = 'http://localhost:5000/api', api_key: str = 'local-dev-key-change-in-production'):
        self.api_url = api_url
        self.api_key = api_key
        self.last_active_app = None
        self.last_window_title = None
        self.last_activity_time = time.time()
        self.app_start_time = {}  # Track when each app started
        self.known_processes = set()  # Track known processes for launch detection
        self.mouse_moves = 0
        self.key_presses = 0
        self.idle_threshold = 300  # 5 minutes
        self._initialize_process_tracking()
        
    def get_active_window(self) -> Optional[Dict]:
        """Get currently active window information."""
        try:
            if platform.system() == 'Linux' and HAS_X11:
                return self._get_active_window_linux()
            elif platform.system() == 'Windows' and HAS_WIN32:
                return self._get_active_window_windows()
            else:
                # Fallback: use process info
                return self._get_active_process()
        except Exception as e:
            return None
    
    def _get_active_window_linux(self) -> Optional[Dict]:
        """Get active window on Linux using X11 with enhanced information."""
        try:
            display = Xlib.display.Display()
            root = display.screen().root
            window = root.get_full_property(
                display.intern_atom('_NET_ACTIVE_WINDOW'),
                X.AnyPropertyType
            ).value[0]
            
            if window:
                window_obj = display.create_resource_object('window', window)
                window_name = window_obj.get_wm_name()
                window_class = window_obj.get_wm_class()
                
                # Get process ID if available
                pid = None
                try:
                    pid_prop = window_obj.get_full_property(
                        display.intern_atom('_NET_WM_PID'),
                        X.AnyPropertyType
                    )
                    if pid_prop:
                        pid = pid_prop.value[0]
                except:
                    pass
                
                # Get executable path if we have PID
                exe_path = None
                app_name = window_class[0] if window_class else 'Unknown'
                if pid:
                    try:
                        proc = psutil.Process(pid)
                        exe_path = proc.exe()
                        app_name = proc.name()  # Use process name instead of class
                    except:
                        pass
                
                return {
                    'title': window_name or 'Unknown',
                    'class': window_class[0] if window_class else 'Unknown',
                    'app': app_name,
                    'pid': pid,
                    'exe_path': exe_path
                }
        except Exception as e:
            return None
    
    def _get_active_window_windows(self) -> Optional[Dict]:
        """Get active window on Windows."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            
            return {
                'title': title,
                'app': process.name(),
                'pid': pid
            }
        except:
            return None
    
    def _get_active_process(self) -> Optional[Dict]:
        """Fallback: get most CPU-intensive process."""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu': proc.info['cpu_percent'] or 0
                    })
                except:
                    continue
            
            if processes:
                top_process = max(processes, key=lambda x: x['cpu'])
                return {
                    'app': top_process['name'],
                    'pid': top_process['pid']
                }
        except:
            pass
        return None
    
    def log_action(self, action_type: str, context: Dict):
        """Log action to backend."""
        try:
            response = requests.post(
                f'{self.api_url}/log-action',
                json={
                    'source': 'system',
                    'action_type': action_type,
                    'context': context,
                    'timestamp': time.time()
                },
                headers={'X-API-Key': self.api_key},
                timeout=2
            )
            return response.status_code == 201
        except:
            return False
    
    def _initialize_process_tracking(self):
        """Initialize tracking of running processes."""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    self.known_processes.add(proc.info['pid'])
                except:
                    continue
        except:
            pass
    
    def _detect_new_apps(self):
        """Detect newly launched applications."""
        try:
            current_pids = set()
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'create_time']):
                try:
                    pid = proc.info['pid']
                    current_pids.add(pid)
                    
                    # Check if this is a new process
                    if pid not in self.known_processes:
                        # New app launched!
                        app_name = proc.info['name']
                        exe_path = proc.info.get('exe', '')
                        create_time = proc.info.get('create_time', time.time())
                        
                        # Only log GUI applications (filter out system processes)
                        if self._is_gui_app(app_name, exe_path):
                            self.log_action('app_launch', {
                                'app': app_name,
                                'exe_path': exe_path,
                                'pid': pid,
                                'launch_time': create_time,
                                'timestamp': time.time()
                            })
                        
                        self.known_processes.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Remove dead processes
            self.known_processes = self.known_processes.intersection(current_pids)
        except Exception as e:
            pass
    
    def _is_gui_app(self, app_name: str, exe_path: str) -> bool:
        """Check if process is likely a GUI application."""
        # Filter out system processes, daemons, etc.
        system_keywords = [
            'systemd', 'kernel', 'dbus', 'gdm', 'pulseaudio', 'pipewire',
            'gnome-shell', 'kde', 'xorg', 'wayland', 'compositor',
            'ssh', 'bash', 'zsh', 'sh', 'python', 'node', 'npm',
            'system', 'daemon', 'service'
        ]
        
        app_lower = app_name.lower()
        exe_lower = exe_path.lower() if exe_path else ''
        
        # If it contains system keywords, it's probably not a user app
        for keyword in system_keywords:
            if keyword in app_lower or keyword in exe_lower:
                return False
        
        # If it's a common GUI app pattern, it's likely a GUI app
        gui_patterns = [
            'code', 'chrome', 'firefox', 'gimp', 'libreoffice', 'gedit',
            'nautilus', 'dolphin', 'thunar', 'file', 'editor', 'browser',
            'terminal', 'gnome-terminal', 'konsole', 'alacritty', 'kitty'
        ]
        
        for pattern in gui_patterns:
            if pattern in app_lower or pattern in exe_lower:
                return True
        
        # Default: assume it's a GUI app if we can't determine
        return True
    
    def track_app_switch(self):
        """Track application switches and window changes with enhanced details."""
        active_window = self.get_active_window()
        if not active_window:
            return
        
        current_app = active_window.get('app', 'Unknown')
        current_title = active_window.get('title', '')
        current_pid = active_window.get('pid')
        
        # Track app switch
        if current_app != self.last_active_app:
            if self.last_active_app:
                # Calculate duration on previous app
                duration = time.time() - self.last_activity_time
                
                self.log_action('app_switch', {
                    'from_app': self.last_active_app,
                    'to_app': current_app,
                    'duration_on_previous': round(duration, 2),
                    'window_title': current_title,
                    'app_pid': current_pid,
                    'exe_path': active_window.get('exe_path', ''),
                    'timestamp': time.time()
                })
            
            # Track app start time
            if current_app not in self.app_start_time:
                self.app_start_time[current_app] = time.time()
        
        # Track window title changes (same app, different window)
        if current_app == self.last_active_app and current_title != self.last_window_title:
            if self.last_window_title:
                self.log_action('window_change', {
                    'app': current_app,
                    'from_title': self.last_window_title,
                    'to_title': current_title,
                    'app_pid': current_pid,
                    'timestamp': time.time()
                })
        
        # Track continuous app usage (every 30 seconds)
        if current_app in self.app_start_time:
            usage_duration = time.time() - self.app_start_time[current_app]
            if int(time.time()) % 30 == 0:  # Every 30 seconds
                self.log_action('app_usage', {
                    'app': current_app,
                    'window_title': current_title,
                    'usage_duration': round(usage_duration, 2),
                    'app_pid': current_pid,
                    'exe_path': active_window.get('exe_path', ''),
                    'timestamp': time.time()
                })
        
        self.last_active_app = current_app
        self.last_window_title = current_title
        self.last_activity_time = time.time()
    
    def track_idle(self):
        """Track idle periods."""
        idle_time = time.time() - self.last_activity_time
        
        if idle_time > self.idle_threshold:
            self.log_action('idle_detection', {
                'idle_duration': idle_time,
                'threshold': self.idle_threshold,
                'timestamp': time.time()
            })
            self.last_activity_time = time.time()  # Reset
    
    def track_screen_time(self):
        """Track screen time per application."""
        active_window = self.get_active_window()
        if active_window:
            app = active_window.get('app', 'Unknown')
            self.log_action('screen_time', {
                'app': app,
                'duration': 60,  # Log every minute
                'timestamp': time.time()
            })
    
    def run(self, interval: int = 2):
        """Run the logger daemon with comprehensive tracking."""
        print(f"🖥️  System Logger started (checking every {interval}s)")
        print(f"   Tracking: App launches, switches, window changes, idle periods")
        
        last_app_detect = time.time()
        last_screen_time = time.time()
        
        while True:
            try:
                # Track app switches and window changes (frequent)
                self.track_app_switch()
                
                # Detect new app launches (every 5 seconds)
                if time.time() - last_app_detect >= 5:
                    self._detect_new_apps()
                    last_app_detect = time.time()
                
                # Track idle periods
                self.track_idle()
                
                # Track screen time every minute
                if time.time() - last_screen_time >= 60:
                    self.track_screen_time()
                    last_screen_time = time.time()
                
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n🛑 System Logger stopped")
                break
            except Exception as e:
                print(f"Error in system logger: {e}")
                time.sleep(interval)


if __name__ == '__main__':
    logger = SystemLogger()
    logger.run(interval=5)



