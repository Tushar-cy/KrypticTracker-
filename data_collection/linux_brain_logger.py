"""
Linux "Second Brain" Logger
Comprehensive logging of all meaningful activities on Linux for neural network training.
"""

import time
import json
import requests
import psutil
import subprocess
import os
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Tuple
import re
import xml.etree.ElementTree as ET
import ast
from collections import Counter

try:
    import Xlib.display
    from Xlib import X
    HAS_X11 = True
except ImportError:
    HAS_X11 = False
    print("Warning: X11 not available")


class LinuxBrainLogger:
    """
    Comprehensive Linux activity logger - tracks everything for "second brain" feel.
    """
    
    def __init__(self, api_url: str = 'http://localhost:5000/api', api_key: str = 'local-dev-key-change-in-production'):
        self.api_url = api_url
        self.api_key = api_key
        self.last_active_app = None
        self.last_window_title = None
        self.last_terminal_command = None
        self.last_git_repo = None
        self.known_processes = set()
        self.action_counts = Counter()
        self.feed_counts = Counter()
        self.last_log_summary = time.time()
        self.summary_interval = 20  # seconds between log summaries
        
        # Shell history tracking
        self.home = Path.home()
        self.zsh_history_file = self.home / '.zsh_history'
        self.bash_history_file = self.home / '.bash_history'
        self.fish_history_file = self.home / '.local/share/fish/fish_history'
        self.history_positions = {}  # Track last read position for each history file
        
        # Browser history tracking
        self.chrome_history_path = self.home / '.config/google-chrome/Default/History'
        self.firefox_profile_path = self.home / '.mozilla/firefox'
        
        # Recent files tracking
        self.recent_files_path = self.home / '.local/share/recently-used.xbel'
        
        # Git repos tracking
        self.tracked_git_repos = set()
        self.git_history_markers: Dict[str, int] = {}
        self.git_cli_history_file = self.home / '.config/git/command-history'
        self.git_cli_history_position = 0
        
        # VS Code recent files
        self.vscode_history_path = self.home / '.config/Code/User/History'

        # Package manager histories
        self.npm_logs_dir = self.home / '.npm/_logs'
        self.processed_npm_logs: Dict[str, float] = {}
        self.pip_log_files = [
            self.home / '.cache/pip/pip.log',
            self.home / '.cache/pip/log/debug.log',
            self.home / '.pip/pip.log'
        ]
        self.pip_log_positions: Dict[str, int] = {}

        # Python REPL history
        self.python_history_file = self.home / '.python_history'
        self.python_history_position = 0
        
        self._initialize_tracking()
    
    def _initialize_tracking(self):
        """Initialize tracking state."""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    self.known_processes.add(proc.info['pid'])
                except:
                    continue
        except:
            pass

        try:
            cwd_repo = self._get_git_repo_from_path(os.getcwd())
            if cwd_repo:
                self.tracked_git_repos.add(cwd_repo)
        except:
            pass
    
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
            success = response.status_code == 201
            if success:
                self._record_log_summary(action_type, context)
            return success
        except:
            return False

    def _infer_feed_label(self, action_type: str, context: Dict) -> Optional[str]:
        """Infer a human-friendly label for log summaries."""
        if not context:
            return None
        
        priority_keys = [
            ('shell', lambda v: f"{v} shell"),
            ('browser', lambda v: f"{v} browser"),
            ('package_manager', lambda v: f"{v} packages"),
            ('git_command', lambda v: f"git {v}"),
            ('git_repo', lambda v: Path(v).name if v else None),
            ('app', lambda v: v),
            ('source_file', lambda v: Path(v).name if v else v),
            ('file_path', lambda v: Path(v).name if v else v),
        ]
        
        for key, formatter in priority_keys:
            value = context.get(key)
            if value:
                try:
                    label = formatter(value)
                except Exception:
                    label = value
                if label:
                    return str(label)
        return action_type

    def _record_log_summary(self, action_type: str, context: Dict):
        """Track counts and periodically print a summary for logs/system_logger.log."""
        self.action_counts[action_type] += 1
        feed_label = self._infer_feed_label(action_type, context)
        if feed_label:
            self.feed_counts[feed_label] += 1
        
        now = time.time()
        if now - self.last_log_summary < self.summary_interval:
            return
        
        total = sum(self.action_counts.values())
        top_actions = ', '.join(f"{name}:{count}" for name, count in self.action_counts.most_common(3))
        top_feeds = ', '.join(f"{name}:{count}" for name, count in self.feed_counts.most_common(3))
        preview = context.get('full_command') or context.get('url') or context.get('file_path') \
            or context.get('title') or context.get('command')
        if isinstance(preview, str) and len(preview) > 60:
            preview = preview[:57] + '…'
        
        stamp = datetime.now().strftime('%H:%M:%S')
        summary = f"[{stamp}] {total} actions • top actions [{top_actions}]"
        if top_feeds:
            summary += f" • feeds [{top_feeds}]"
        summary += f" • last={action_type}"
        if feed_label:
            summary += f" ({feed_label})"
        if preview:
            summary += f" -> {preview}"
        
        print(summary)
        self.last_log_summary = now
    
    # ==================== FILE OPERATIONS ====================
    
    def track_file_operations(self):
        """Track file operations using inotify (if available) or process monitoring."""
        try:
            # Track recently modified files
            for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                try:
                    if proc.info['open_files']:
                        for file_info in proc.info['open_files']:
                            file_path = file_info.path
                            if self._is_user_file(file_path):
                                self.log_action('file_access', {
                                    'file_path': file_path,
                                    'app': proc.info['name'],
                                    'pid': proc.info['pid'],
                                    'operation': 'open'
                                })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            pass
    
    def _is_user_file(self, file_path: str) -> bool:
        """Check if file is a user file (not system file)."""
        user_home = str(Path.home())
        system_paths = ['/proc', '/sys', '/dev', '/tmp', '/var/log']
        
        if not file_path.startswith(user_home):
            return False
        
        for sys_path in system_paths:
            if file_path.startswith(sys_path):
                return False
        
        return True
    
    # ==================== TERMINAL COMMANDS ====================
    
    def track_terminal_commands(self):
        """Track terminal commands from all shell histories (zsh, bash, fish)."""
        # Track zsh history (with timestamps)
        self._track_zsh_history()
        
        # Track bash history
        self._track_bash_history()
        
        # Track fish history
        self._track_fish_history()
    
    def _track_zsh_history(self):
        """Track zsh history with timestamp parsing."""
        if not self.zsh_history_file.exists():
            return
        
        try:
            # zsh history format: ': timestamp:0;command'
            with open(self.zsh_history_file, 'rb') as f:
                # Get current file size to track position
                f.seek(0, 2)  # Seek to end
                current_size = f.tell()
                
                # Get last known position
                last_pos = self.history_positions.get('zsh', 0)
                
                # If file grew, read new lines
                if current_size > last_pos:
                    f.seek(last_pos)
                    new_lines = f.read().decode('utf-8', errors='ignore').split('\n')
                    
                    for line in new_lines:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        # Parse zsh history format: ': timestamp:0;command'
                        # Format: ': 1234567890:0;command'
                        match = re.match(r':\s*(\d+):\d+;(.+)', line)
                        if match:
                            timestamp = int(match.group(1))
                            command = match.group(2).strip()
                            
                            if command and command != self.last_terminal_command:
                                self._process_command(command, timestamp, 'zsh')
                                self.last_terminal_command = command
                    
                    self.history_positions['zsh'] = current_size
        except Exception as e:
            pass
    
    def _track_bash_history(self):
        """Track bash history (no timestamps, use current time)."""
        if not self.bash_history_file.exists():
            return
        
        try:
            current_size = self.bash_history_file.stat().st_size
            last_pos = self.history_positions.get('bash', 0)
            
            if current_size > last_pos:
                with open(self.bash_history_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_pos)
                    new_lines = f.read().split('\n')
                    
                    for line in new_lines:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        if line and line != self.last_terminal_command:
                            self._process_command(line, time.time(), 'bash')
                            self.last_terminal_command = line
                    
                    self.history_positions['bash'] = current_size
        except Exception as e:
            pass
    
    def _track_fish_history(self):
        """Track fish shell history."""
        if not self.fish_history_file.exists():
            return
        
        try:
            current_size = self.fish_history_file.stat().st_size
            last_pos = self.history_positions.get('fish', 0)
            
            if current_size > last_pos:
                with open(self.fish_history_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_pos)
                    content = f.read()
                    
                    # Fish history format: '- cmd: command\n   when: timestamp\n'
                    # Parse commands
                    commands = re.findall(r'- cmd: (.+?)\n   when: (\d+)', content)
                    
                    for cmd, timestamp_str in commands:
                        if cmd and cmd != self.last_terminal_command:
                            timestamp = int(timestamp_str)
                            self._process_command(cmd, timestamp, 'fish')
                            self.last_terminal_command = cmd
                    
                    self.history_positions['fish'] = current_size
        except Exception as e:
            pass

    def track_python_repl_history(self):
        """Track Python REPL history from ~/.python_history."""
        if not self.python_history_file.exists():
            return
        
        try:
            current_size = self.python_history_file.stat().st_size
            last_pos = self.python_history_position
            
            if current_size > last_pos:
                with open(self.python_history_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                
                for line in new_lines:
                    command = line.strip()
                    if not command:
                        continue
                    
                    self.log_action('python_repl_command', {
                        'code': command[:500],
                        'source_file': str(self.python_history_file),
                        'timestamp': time.time()
                    })
                
                self.python_history_position = current_size
        except Exception:
            pass

    def track_git_cli_history(self):
        """Track git command history from git's command-history file."""
        if not self.git_cli_history_file.exists():
            return
        
        try:
            current_size = self.git_cli_history_file.stat().st_size
            last_pos = self.git_cli_history_position
            
            if current_size > last_pos:
                with open(self.git_cli_history_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_pos)
                    lines = f.readlines()
                
                for raw_line in lines:
                    line = raw_line.strip()
                    if not line:
                        continue
                    
                    timestamp = time.time()
                    command = line
                    
                    if '\t' in line:
                        meta, command = line.split('\t', 1)
                        meta_parts = meta.split()
                        try:
                            timestamp = int(meta_parts[0])
                        except:
                            timestamp = time.time()
                    
                    self.log_action('git_cli_history', {
                        'command': command.strip()[:500],
                        'timestamp': timestamp,
                        'source_file': str(self.git_cli_history_file)
                    })
                
                self.git_cli_history_position = current_size
        except Exception:
            pass
    
    def _process_command(self, command: str, timestamp: float, shell: str):
        """Process a terminal command and log it."""
        if not command or len(command) < 2:
            return
        
        # Parse command
        command_parts = command.split()
        if not command_parts:
            return
        
        cmd = command_parts[0]
        args = ' '.join(command_parts[1:]) if len(command_parts) > 1 else ''
        
        # Detect command category
        category = self._categorize_command(cmd)
        
        context = {
            'command': cmd,
            'args': args[:200],  # Limit length
            'full_command': command[:500],
            'shell': shell,
            'category': category,
            'timestamp': timestamp
        }
        
        # Add working directory if available
        try:
            cwd = os.getcwd()
            if cwd:
                context['working_directory'] = cwd
                # Check if we're in a git repo
                git_repo = self._get_git_repo_from_path(cwd)
                if git_repo:
                    context['git_repo'] = git_repo
        except:
            pass
        
        self.log_action('terminal_command', context)
        
        # Detect git commands
        if cmd == 'git' and args:
            self._track_git_command(args, timestamp)
        
        # Detect package manager commands
        if cmd in ['npm', 'pip', 'pip3', 'yarn', 'pnpm', 'cargo', 'apt', 'apt-get', 'pacman', 'yay', 'paru']:
            self._track_package_manager_command(cmd, args, timestamp)
    
    def _categorize_command(self, cmd: str) -> str:
        """Categorize command for better understanding."""
        categories = {
            'git': 'version_control',
            'cd': 'navigation',
            'ls': 'navigation',
            'cat': 'file_operation',
            'vim': 'editing',
            'nano': 'editing',
            'code': 'editing',
            'python': 'execution',
            'node': 'execution',
            'npm': 'package_manager',
            'pip': 'package_manager',
            'docker': 'containerization',
            'ssh': 'remote',
            'curl': 'network',
            'wget': 'network',
            'grep': 'search',
            'find': 'search',
        }
        
        return categories.get(cmd, 'other')
    
    def _get_git_repo_from_path(self, path: str) -> Optional[str]:
        """Check if path is inside a git repo and return repo root."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True,
                text=True,
                timeout=1,
                cwd=path
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None
    
    def _track_git_command(self, args: str, timestamp: float):
        """Track git-specific commands with enhanced context."""
        git_commands = {
            'commit': 'git_commit',
            'push': 'git_push',
            'pull': 'git_pull',
            'clone': 'git_clone',
            'branch': 'git_branch',
            'checkout': 'git_checkout',
            'merge': 'git_merge',
            'add': 'git_add',
            'status': 'git_status',
            'log': 'git_log',
            'diff': 'git_diff',
        }
        
        for cmd, action_type in git_commands.items():
            if args.startswith(cmd):
                # Try to extract repo path
                repo_path = self._get_current_git_repo()
                
                # Extract branch if available
                branch = None
                try:
                    result = subprocess.run(
                        ['git', 'branch', '--show-current'],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )
                    if result.returncode == 0:
                        branch = result.stdout.strip()
                except:
                    pass
                
                self.log_action(action_type, {
                    'git_command': cmd,
                    'args': args[:200],
                    'repo_path': repo_path,
                    'branch': branch,
                    'timestamp': timestamp
                })
                break
    
    def _track_package_manager_command(self, cmd: str, args: str, timestamp: float):
        """Track package manager commands."""
        action_type = 'package_manager_command'
        
        # Detect operation type
        operation = 'unknown'
        if any(op in args for op in ['install', 'i', 'add']):
            operation = 'install'
        elif any(op in args for op in ['uninstall', 'remove', 'rm']):
            operation = 'uninstall'
        elif any(op in args for op in ['update', 'upgrade', 'up']):
            operation = 'update'
        elif any(op in args for op in ['list', 'ls', 'show']):
            operation = 'list'
        elif any(op in args for op in ['search', 'find']):
            operation = 'search'
        
        # Extract package name if available
        package_name = None
        args_parts = args.split()
        if args_parts and operation in ['install', 'uninstall', 'add', 'remove']:
            # Package name is usually the first non-flag argument
            for part in args_parts:
                if not part.startswith('-') and part not in ['install', 'uninstall', 'add', 'remove']:
                    package_name = part
                    break
        
        self.log_action(action_type, {
            'package_manager': cmd,
            'operation': operation,
            'package_name': package_name,
            'args': args[:200],
            'timestamp': timestamp
        })

    def _extract_npm_command(self, log_text: str) -> Optional[str]:
        """Extract npm command from npm debug logs."""
        for line in log_text.splitlines():
            if 'verbose cli [' in line:
                try:
                    start = line.index('[')
                    end = line.rindex(']') + 1
                    cli_array = ast.literal_eval(line[start:end])
                    if len(cli_array) >= 3:
                        return f"npm {' '.join(cli_array[2:])}".strip()
                except:
                    continue
            if line.strip().startswith('argv "'):
                matches = re.findall(r'"([^"]+)"', line)
                if len(matches) >= 3:
                    return 'npm ' + ' '.join(matches[2:])
        return None

    def track_npm_history(self):
        """Track npm CLI history from ~/.npm/_logs."""
        if not self.npm_logs_dir.exists():
            return
        
        try:
            for log_file in sorted(self.npm_logs_dir.glob('*-debug.log')):
                log_key = str(log_file)
                current_mtime = log_file.stat().st_mtime
                last_mtime = self.processed_npm_logs.get(log_key, 0)
                
                if current_mtime <= last_mtime:
                    continue
                
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    command_line = self._extract_npm_command(content)
                    if command_line:
                        self.log_action('npm_history_command', {
                            'command': command_line[:500],
                            'log_file': log_key,
                            'timestamp': current_mtime
                        })
                        self.processed_npm_logs[log_key] = current_mtime
                except Exception:
                    continue
        except Exception:
            pass

    def track_pip_history(self):
        """Track pip install history from pip debug logs."""
        try:
            for log_file in self.pip_log_files:
                if not log_file.exists():
                    continue
                
                log_key = str(log_file)
                current_size = log_file.stat().st_size
                last_pos = self.pip_log_positions.get(log_key, 0)
                
                if current_size <= last_pos:
                    continue
                
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                
                for line in new_lines:
                    if 'Running command' in line:
                        command = line.split('Running command', 1)[1].strip()
                        if not command:
                            continue
                        
                        timestamp = time.time()
                        match = re.match(r'(\d{4}-\d{2}-\d{2}T[\d:.+-]+)', line)
                        if match:
                            try:
                                timestamp = datetime.fromisoformat(match.group(1)).timestamp()
                            except:
                                timestamp = time.time()
                        
                        self.log_action('pip_history_command', {
                            'command': command[:500],
                            'log_file': log_key,
                            'timestamp': timestamp
                        })
                
                self.pip_log_positions[log_key] = current_size
        except Exception:
            pass
    
    def _get_current_git_repo(self) -> Optional[str]:
        """Get current git repository path."""
        try:
            cwd = os.getcwd()
            return self._get_git_repo_from_path(cwd)
        except:
            pass
        return None
    
    # ==================== BROWSER HISTORY ====================
    
    def track_browser_history(self):
        """Track browser history from Chrome and Firefox."""
        self._track_chrome_history()
        self._track_firefox_history()
    
    def _track_chrome_history(self):
        """Track Chrome browsing history."""
        if not self.chrome_history_path.exists():
            return
        
        try:
            # Chrome locks the DB, so we need to copy it first
            import shutil
            temp_db = self.chrome_history_path.parent / 'History_temp'
            
            try:
                shutil.copy2(self.chrome_history_path, temp_db)
                
                conn = sqlite3.connect(str(temp_db))
                cursor = conn.cursor()
                
                # Get recent visits (last 24 hours)
                # Chrome uses microseconds since 1601-01-01 00:00:00 UTC
                chrome_epoch = 11644473600000000  # microseconds since 1601-01-01
                unix_now = time.time()
                chrome_now = int(unix_now * 1000000) + chrome_epoch
                cutoff_time = chrome_now - int(86400 * 1000000)  # 24 hours ago in Chrome time
                
                cursor.execute("""
                    SELECT urls.url, urls.title, urls.visit_count, 
                           visits.visit_time, visits.transition
                    FROM urls
                    JOIN visits ON urls.id = visits.url
                    WHERE visits.visit_time > ?
                    ORDER BY visits.visit_time DESC
                    LIMIT 50
                """, (cutoff_time,))
                
                visits = cursor.fetchall()
                conn.close()
                
                # Log new visits
                for url, title, visit_count, visit_time, transition in visits:
                    # Convert Chrome timestamp (microseconds since 1601-01-01) to Unix timestamp
                    unix_timestamp = (visit_time - chrome_epoch) / 1000000.0
                    
                    self.log_action('browser_visit', {
                        'browser': 'chrome',
                        'url': url[:500],
                        'title': title[:200] if title else '',
                        'visit_count': visit_count,
                        'transition': transition,
                        'timestamp': unix_timestamp
                    })
                
                # Clean up temp file
                if temp_db.exists():
                    temp_db.unlink()
            except sqlite3.OperationalError:
                # DB is locked, skip this cycle
                pass
        except Exception as e:
            pass
    
    def _track_firefox_history(self):
        """Track Firefox browsing history."""
        if not self.firefox_profile_path.exists():
            return
        
        try:
            # Find default profile
            profiles = list(self.firefox_profile_path.glob('*.default*'))
            if not profiles:
                return
            
            profile_path = profiles[0]
            places_db = profile_path / 'places.sqlite'
            
            if not places_db.exists():
                return
            
            # Copy DB to avoid locks
            import shutil
            temp_db = places_db.parent / 'places_temp.sqlite'
            
            try:
                shutil.copy2(places_db, temp_db)
                
                conn = sqlite3.connect(str(temp_db))
                cursor = conn.cursor()
                
                # Get recent visits (last 24 hours)
                cutoff_time = int((time.time() - 86400) * 1000000)  # microseconds
                
                cursor.execute("""
                    SELECT moz_places.url, moz_places.title, moz_places.visit_count,
                           moz_historyvisits.visit_date, moz_historyvisits.visit_type
                    FROM moz_places
                    JOIN moz_historyvisits ON moz_places.id = moz_historyvisits.place_id
                    WHERE moz_historyvisits.visit_date > ?
                    ORDER BY moz_historyvisits.visit_date DESC
                    LIMIT 50
                """, (cutoff_time,))
                
                visits = cursor.fetchall()
                conn.close()
                
                # Log new visits
                for url, title, visit_count, visit_date, visit_type in visits:
                    # Firefox uses microseconds since Unix epoch
                    unix_timestamp = visit_date / 1000000.0
                    
                    self.log_action('browser_visit', {
                        'browser': 'firefox',
                        'url': url[:500],
                        'title': title[:200] if title else '',
                        'visit_count': visit_count,
                        'visit_type': visit_type,
                        'timestamp': unix_timestamp
                    })
                
                # Clean up temp file
                if temp_db.exists():
                    temp_db.unlink()
            except sqlite3.OperationalError:
                # DB is locked, skip this cycle
                pass
        except Exception as e:
            pass
    
    # ==================== RECENT FILES ====================
    
    def track_recent_files(self):
        """Track recently accessed files from system."""
        if not self.recent_files_path.exists():
            return
        
        try:
            tree = ET.parse(self.recent_files_path)
            root = tree.getroot()
            
            # Parse recently-used.xbel format
            for item in root.findall('.//{http://www.freedesktop.org/standards/shared-mime-info}bookmark'):
                uri = item.get('href', '')
                if uri.startswith('file://'):
                    file_path = uri.replace('file://', '')
                    # Get modification time
                    added = item.get('added', '')
                    
                    if file_path and self._is_user_file(file_path):
                        self.log_action('recent_file', {
                            'file_path': file_path[:500],
                            'added': added,
                            'timestamp': time.time()
                        })
        except Exception as e:
            pass
    
    # ==================== GIT REPOSITORY TRACKING ====================
    
    def track_git_repos(self):
        """Discover and track git repositories."""
        try:
            # Common locations for git repos
            search_paths = [
                self.home / 'Projects',
                self.home / 'projects',
                self.home / 'code',
                self.home / 'Code',
                self.home / 'workspace',
                self.home / 'Workspace',
                self.home / 'dev',
                self.home / 'Development',
            ]
            
            for base_path in search_paths:
                if not base_path.exists():
                    continue
                
                # Find all .git directories
                for git_dir in base_path.rglob('.git'):
                    if git_dir.is_dir():
                        repo_path = git_dir.parent
                        repo_str = str(repo_path)
                        
                        if repo_str not in self.tracked_git_repos:
                            # Get repo info
                            try:
                                result = subprocess.run(
                                    ['git', 'config', '--get', 'remote.origin.url'],
                                    capture_output=True,
                                    text=True,
                                    timeout=1,
                                    cwd=repo_path
                                )
                                remote_url = result.stdout.strip() if result.returncode == 0 else None
                                
                                # Get current branch
                                result = subprocess.run(
                                    ['git', 'branch', '--show-current'],
                                    capture_output=True,
                                    text=True,
                                    timeout=1,
                                    cwd=repo_path
                                )
                                branch = result.stdout.strip() if result.returncode == 0 else None
                                
                                self.log_action('git_repo_discovered', {
                                    'repo_path': repo_str,
                                    'remote_url': remote_url,
                                    'branch': branch,
                                    'timestamp': time.time()
                                })
                                
                                self.tracked_git_repos.add(repo_str)
                            except:
                                pass
        except Exception as e:
            pass

    def track_git_commit_history(self):
        """Track recent git commits from discovered repositories."""
        if not self.tracked_git_repos:
            return
        
        for repo_path in list(self.tracked_git_repos):
            try:
                repo = Path(repo_path)
                if not repo.exists():
                    continue
                
                result = subprocess.run(
                    ['git', 'log', '-n', '25', '--pretty=format:%ct|%H|%an|%s'],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=repo
                )
                if result.returncode != 0:
                    continue
                
                lines = [line for line in result.stdout.splitlines() if line.strip()]
                if not lines:
                    continue
                
                last_timestamp = self.git_history_markers.get(repo_path, 0)
                new_commits = []
                
                for line in lines:
                    parts = line.split('|', 3)
                    if len(parts) < 4:
                        continue
                    timestamp, commit_hash, author, message = parts
                    try:
                        ts = int(timestamp.strip())
                    except:
                        ts = int(time.time())
                    
                    if ts <= last_timestamp:
                        continue
                    
                    new_commits.append((ts, commit_hash.strip(), author.strip(), message.strip()))
                
                if not new_commits:
                    continue
                
                for ts, commit_hash, author, message in reversed(new_commits[-10:]):
                    self.log_action('git_commit_history', {
                        'repo_path': repo_path,
                        'commit': commit_hash,
                        'author': author,
                        'message': message[:300],
                        'timestamp': ts
                    })
                
                self.git_history_markers[repo_path] = max(ts for ts, *_ in new_commits)
            except Exception:
                continue
    
    # ==================== VS CODE RECENT FILES ====================
    
    def track_vscode_recent_files(self):
        """Track VS Code recently opened files."""
        if not self.vscode_history_path.exists():
            return
        
        try:
            # VS Code stores recent files in workspaceStorage
            workspace_storage = self.home / '.config/Code/User/workspaceStorage'
            if workspace_storage.exists():
                # Each workspace has a storage.json with recent files
                for workspace_dir in workspace_storage.iterdir():
                    storage_file = workspace_dir / 'workspace.json'
                    if storage_file.exists():
                        try:
                            with open(storage_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                # VS Code stores recent files in various keys
                                # This is a simplified version
                                if 'recentlyOpened' in data:
                                    for item in data['recentlyOpened']:
                                        if 'fileUri' in item:
                                            file_path = item['fileUri'].replace('file://', '')
                                            if self._is_user_file(file_path):
                                                self.log_action('vscode_recent_file', {
                                                    'file_path': file_path[:500],
                                                    'timestamp': time.time()
                                                })
                        except:
                            pass
        except Exception as e:
            pass
    
    # ==================== NETWORK ACTIVITY ====================
    
    def track_network_activity(self):
        """Track network connections and activity."""
        try:
            connections = psutil.net_connections(kind='inet')
            active_connections = []
            
            for conn in connections:
                if conn.status == 'ESTABLISHED':
                    try:
                        proc = psutil.Process(conn.pid)
                        app_name = proc.name()
                        
                        # Only track user applications
                        if self._is_gui_app(app_name, ''):
                            active_connections.append({
                                'app': app_name,
                                'local_addr': f"{conn.laddr.ip}:{conn.laddr.port}",
                                'remote_addr': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                                'status': conn.status
                            })
                    except:
                        continue
            
            if active_connections:
                self.log_action('network_activity', {
                    'connections': active_connections[:10],  # Limit to 10
                    'total_connections': len(active_connections),
                    'timestamp': time.time()
                })
        except Exception as e:
            pass
    
    # ==================== SYSTEM RESOURCES ====================
    
    def track_system_resources(self):
        """Track CPU, memory, disk usage patterns."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get top processes by CPU
            top_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    proc.info['cpu_percent'] = proc.cpu_percent(interval=0.1)
                    if proc.info['cpu_percent'] > 1.0:  # Only significant usage
                        top_processes.append({
                            'name': proc.info['name'],
                            'cpu': round(proc.info['cpu_percent'], 1),
                            'memory': round(proc.info['memory_percent'], 1)
                        })
                except:
                    continue
            
            top_processes.sort(key=lambda x: x['cpu'], reverse=True)
            
            self.log_action('system_resources', {
                'cpu_percent': round(cpu_percent, 1),
                'memory_percent': round(memory.percent, 1),
                'disk_percent': round(disk.percent, 1),
                'top_processes': top_processes[:5],  # Top 5
                'timestamp': time.time()
            })
        except Exception as e:
            pass
    
    # ==================== FOCUS SESSIONS ====================
    
    def track_focus_sessions(self):
        """Track focused work sessions (extended time in same app)."""
        active_window = self._get_active_window()
        if not active_window:
            return
        
        current_app = active_window.get('app', 'Unknown')
        
        # If same app for > 5 minutes, it's a focus session
        if current_app == self.last_active_app:
            if hasattr(self, 'focus_start_time'):
                focus_duration = time.time() - self.focus_start_time
                if focus_duration > 300:  # 5 minutes
                    if not hasattr(self, 'focus_logged') or not self.focus_logged:
                        self.log_action('focus_session', {
                            'app': current_app,
                            'window_title': active_window.get('title', ''),
                            'duration': round(focus_duration, 2),
                            'timestamp': time.time()
                        })
                        self.focus_logged = True
            else:
                self.focus_start_time = time.time()
                self.focus_logged = False
        else:
            self.focus_start_time = time.time()
            self.focus_logged = False
    
    # ==================== APP LAUNCHES ====================
    
    def track_app_launches(self):
        """Track when new applications are launched."""
        try:
            current_pids = set()
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'create_time', 'ppid']):
                try:
                    pid = proc.info['pid']
                    current_pids.add(pid)
                    
                    if pid not in self.known_processes:
                        app_name = proc.info['name']
                        exe_path = proc.info.get('exe', '')
                        
                        if self._is_gui_app(app_name, exe_path):
                            self.log_action('app_launch', {
                                'app': app_name,
                                'exe_path': exe_path,
                                'pid': pid,
                                'parent_pid': proc.info.get('ppid'),
                                'launch_time': proc.info.get('create_time', time.time()),
                                'timestamp': time.time()
                            })
                        
                        self.known_processes.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            self.known_processes = self.known_processes.intersection(current_pids)
        except Exception as e:
            pass
    
    # ==================== WINDOW TRACKING ====================
    
    def _get_active_window(self) -> Optional[Dict]:
        """Get currently active window."""
        if not HAS_X11:
            return None
        
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
                
                exe_path = None
                app_name = window_class[0] if window_class else 'Unknown'
                if pid:
                    try:
                        proc = psutil.Process(pid)
                        exe_path = proc.exe()
                        app_name = proc.name()
                    except:
                        pass
                
                return {
                    'title': window_name or 'Unknown',
                    'class': window_class[0] if window_class else 'Unknown',
                    'app': app_name,
                    'pid': pid,
                    'exe_path': exe_path
                }
        except:
            pass
        
        return None
    
    def track_window_changes(self):
        """Track window focus and title changes."""
        active_window = self._get_active_window()
        if not active_window:
            return
        
        current_app = active_window.get('app', 'Unknown')
        current_title = active_window.get('title', '')
        
        # App switch
        if current_app != self.last_active_app:
            if self.last_active_app:
                self.log_action('app_switch', {
                    'from_app': self.last_active_app,
                    'to_app': current_app,
                    'window_title': current_title,
                    'app_pid': active_window.get('pid'),
                    'timestamp': time.time()
                })
            self.last_active_app = current_app
        
        # Window title change
        if current_app == self.last_active_app and current_title != self.last_window_title:
            if self.last_window_title:
                self.log_action('window_change', {
                    'app': current_app,
                    'from_title': self.last_window_title,
                    'to_title': current_title,
                    'timestamp': time.time()
                })
            self.last_window_title = current_title
    
    # ==================== UTILITY METHODS ====================
    
    def _is_gui_app(self, app_name: str, exe_path: str) -> bool:
        """Check if process is a GUI application."""
        system_keywords = [
            'systemd', 'kernel', 'dbus', 'gdm', 'pulseaudio', 'pipewire',
            'gnome-shell', 'kde', 'xorg', 'wayland', 'compositor',
            'ssh', 'bash', 'zsh', 'sh', 'python', 'node', 'npm',
            'system', 'daemon', 'service'
        ]
        
        app_lower = app_name.lower()
        exe_lower = exe_path.lower() if exe_path else ''
        
        for keyword in system_keywords:
            if keyword in app_lower or keyword in exe_lower:
                return False
        
        return True
    
    # ==================== MAIN LOOP ====================
    
    def run(self, interval: int = 3):
        """Run the comprehensive logger."""
        print("🧠 Linux Brain Logger started!")
        print("   Tracking: Shell History (zsh/bash/fish), Browser History, Recent Files,")
        print("            Git Repos + Commits, VS Code Files, Files, Terminal, Git CLI,")
        print("            npm/pip/python histories, Network, Resources, Focus Sessions, Apps, Windows")
        
        # Initialize history positions
        for hist_file, path in [
            ('zsh', self.zsh_history_file),
            ('bash', self.bash_history_file),
            ('fish', self.fish_history_file)
        ]:
            if path.exists():
                self.history_positions[hist_file] = path.stat().st_size
        
        last_file_check = time.time()
        last_terminal_check = time.time()
        last_network_check = time.time()
        last_resources_check = time.time()
        last_app_check = time.time()
        last_browser_check = time.time()
        last_recent_files_check = time.time()
        last_git_repos_check = time.time()
        last_vscode_check = time.time()
        last_git_history_check = time.time()
        last_git_cli_check = time.time()
        last_package_history_check = time.time()
        last_python_history_check = time.time()
        
        while True:
            try:
                # Window tracking (frequent - every interval)
                self.track_window_changes()
                self.track_focus_sessions()
                
                # Terminal commands (every 5 seconds) - now reads zsh, bash, fish
                if time.time() - last_terminal_check >= 5:
                    self.track_terminal_commands()
                    last_terminal_check = time.time()
                
                # File operations (every 10 seconds)
                if time.time() - last_file_check >= 10:
                    self.track_file_operations()
                    last_file_check = time.time()
                
                # Browser history (every 60 seconds)
                if time.time() - last_browser_check >= 60:
                    self.track_browser_history()
                    last_browser_check = time.time()
                
                # Recent files (every 30 seconds)
                if time.time() - last_recent_files_check >= 30:
                    self.track_recent_files()
                    last_recent_files_check = time.time()
                
                # Git repos (every 5 minutes)
                if time.time() - last_git_repos_check >= 300:
                    self.track_git_repos()
                    last_git_repos_check = time.time()

                # Git commit history (every 3 minutes)
                if time.time() - last_git_history_check >= 180:
                    self.track_git_commit_history()
                    last_git_history_check = time.time()
                
                # VS Code recent files (every 30 seconds)
                if time.time() - last_vscode_check >= 30:
                    self.track_vscode_recent_files()
                    last_vscode_check = time.time()

                # Git CLI / python histories (every 20 seconds)
                if time.time() - last_git_cli_check >= 20:
                    self.track_git_cli_history()
                    last_git_cli_check = time.time()
                if time.time() - last_python_history_check >= 20:
                    self.track_python_repl_history()
                    last_python_history_check = time.time()
                
                # Network activity (every 30 seconds)
                if time.time() - last_network_check >= 30:
                    self.track_network_activity()
                    last_network_check = time.time()
                
                # System resources (every 60 seconds)
                if time.time() - last_resources_check >= 60:
                    self.track_system_resources()
                    last_resources_check = time.time()

                # Package manager histories (every 45 seconds)
                if time.time() - last_package_history_check >= 45:
                    self.track_npm_history()
                    self.track_pip_history()
                    last_package_history_check = time.time()
                
                # App launches (every 5 seconds)
                if time.time() - last_app_check >= 5:
                    self.track_app_launches()
                    last_app_check = time.time()
                
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n🛑 Linux Brain Logger stopped")
                break
            except Exception as e:
                print(f"Error in brain logger: {e}")
                time.sleep(interval)


if __name__ == '__main__':
    logger = LinuxBrainLogger()
    logger.run(interval=3)




