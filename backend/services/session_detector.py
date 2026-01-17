"""
Session Detection Service

Automatically detects work sessions from action logs by:
- Grouping actions by time proximity
- Identifying primary project/activity
- Labeling session type (coding, research, debugging)
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import re
from collections import Counter


class SessionDetector:
    """Detects and groups actions into meaningful work sessions."""
    
    def __init__(self, db_connection, session_gap_minutes: int = 15):
        """
        Initialize session detector.
        
        Args:
            db_connection: Database connection
            session_gap_minutes: Minutes of inactivity before starting new session
        """
        self.db = db_connection
        self.session_gap_minutes = session_gap_minutes
        self.session_gap_seconds = session_gap_minutes * 60
    
    def detect_sessions(self, start_time: Optional[float] = None, end_time: Optional[float] = None) -> List[Dict]:
        """
        Detect all sessions within a time range.
        
        Args:
            start_time: Unix timestamp for start (default: 24 hours ago)
            end_time: Unix timestamp for end (default: now)
        
        Returns:
            List of session dictionaries with metadata
        """
        import time
        
        if end_time is None:
            end_time = time.time()
        if start_time is None:
            start_time = end_time - (24 * 3600)  # 24 hours ago
        
        # Get all actions in time range, ordered by timestamp
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT id, timestamp, source, action_type, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        actions = []
        for row in cursor.fetchall():
            import json
            action = {
                'id': row[0],
                'timestamp': row[1],
                'source': row[2],
                'action_type': row[3],
                'context': json.loads(row[4]) if row[4] else {}
            }
            actions.append(action)
        
        if not actions:
            return []
        
        # Group actions into sessions based on time gaps
        sessions = []
        current_session_actions = []
        
        for i, action in enumerate(actions):
            if i == 0:
                current_session_actions.append(action)
                continue
            
            # Check time gap between this action and previous
            time_gap = action['timestamp'] - actions[i-1]['timestamp']
            
            if time_gap > self.session_gap_seconds:
                # Gap too large - finish current session and start new one
                if len(current_session_actions) >= 3:  # Minimum 3 actions for a session
                    session = self._create_session_metadata(current_session_actions)
                    sessions.append(session)
                current_session_actions = [action]
            else:
                current_session_actions.append(action)
        
        # Don't forget the last session
        if len(current_session_actions) >= 3:
            session = self._create_session_metadata(current_session_actions)
            sessions.append(session)
        
        return sessions
    
    def _create_session_metadata(self, actions: List[Dict]) -> Dict:
        """
        Create session metadata from a list of actions.
        
        Args:
            actions: List of action dictionaries
        
        Returns:
            Session metadata dictionary
        """
        start_time = actions[0]['timestamp']
        end_time = actions[-1]['timestamp']
        duration_seconds = end_time - start_time
        duration_minutes = round(duration_seconds / 60, 1)
        
        # Detect primary project
        primary_project = self._detect_primary_project(actions)
        
        # Detect session type
        session_type = self._detect_session_type(actions)
        
        # Count actions by source
        source_counts = Counter(a['source'] for a in actions)
        
        # Count actions by type
        type_counts = Counter(a['action_type'] for a in actions)
        
        # Get unique files/apps/urls
        files_set = set()
        apps_set = set()
        urls_set = set()
        commands_set = set()
        
        for action in actions:
            ctx = action['context']
            if 'file_path' in ctx:
                files_set.add(ctx['file_path'])
            if 'source_file' in ctx:
                files_set.add(ctx['source_file'])
            if 'app' in ctx:
                apps_set.add(ctx['app'])
            if 'url' in ctx:
                urls_set.add(ctx['url'])
            if 'command' in ctx or 'full_command' in ctx:
                cmd = ctx.get('command') or ctx.get('full_command', '')
                if cmd:
                    commands_set.add(cmd)
        
        start_time = actions[0]['timestamp']
        end_time = actions[-1]['timestamp']
        duration_seconds = end_time - start_time
        duration_minutes = round(duration_seconds / 60, 1)
        
        return {
            'start_time': start_time,
            'end_time': end_time,
            'duration_seconds': duration_seconds,
            'duration_minutes': duration_minutes,
            'action_count': len(actions),
            'project': primary_project,
            'session_type': session_type,
            'files_accessed': list(files_set)[:20],  # Top 20 files
            'apps_used': list(apps_set),
            'urls_visited': list(urls_set)[:10],  # Top 10 URLs
            'commands_run': list(commands_set)[:15],  # Top 15 commands
            'metadata': {
                'first_action_type': actions[0]['action_type'] if actions else None,
                'last_action_type': actions[-1]['action_type'] if actions else None,
                'unique_files': len(files_set),
                'unique_apps': len(apps_set),
                'unique_urls': len(urls_set),
                'source_counts': dict(source_counts), # Added back source_counts
                'type_counts': dict(type_counts),     # Added back type_counts
                'action_ids': [a['id'] for a in actions] # Added back action_ids
            }
        }
    
    def _detect_primary_project(self, actions: List[Dict]) -> Optional[str]:
        """
        Detect the primary project from actions.
        
        Looks for:
        - Git repo paths
        - Common file path prefixes
        - Working directories
        """
        git_repos = []
        file_paths = []
        working_dirs = []
        
        for action in actions:
            ctx = action['context']
            
            # Git repos
            if 'git_repo' in ctx and ctx['git_repo']:
                git_repos.append(ctx['git_repo'])
            if 'repo_path' in ctx and ctx['repo_path']:
                git_repos.append(ctx['repo_path'])
            
            # File paths
            if 'file_path' in ctx:
                file_paths.append(ctx['file_path'])
            if 'source_file' in ctx:
                file_paths.append(ctx['source_file'])
            
            # Working directories
            if 'working_directory' in ctx:
                working_dirs.append(ctx['working_directory'])
        
        # Priority 1: Most common git repo
        if git_repos:
            repo_counts = Counter(git_repos)
            most_common_repo = repo_counts.most_common(1)[0][0]
            return Path(most_common_repo).name
        
        # Priority 2: Most common file path prefix
        if file_paths:
            # Find common parent directory
            common_prefix = self._find_common_path_prefix(file_paths)
            if common_prefix:
                return Path(common_prefix).name
        
        # Priority 3: Most common working directory
        if working_dirs:
            dir_counts = Counter(working_dirs)
            most_common_dir = dir_counts.most_common(1)[0][0]
            return Path(most_common_dir).name
        
        return None
    
    def _find_common_path_prefix(self, paths: List[str]) -> Optional[str]:
        """Find the common prefix of file paths."""
        if not paths:
            return None
        
        # Convert to Path objects and get parts
        path_parts = [Path(p).parts for p in paths if p]
        
        if not path_parts:
            return None
        
        # Find common prefix
        min_length = min(len(parts) for parts in path_parts)
        common_parts = []
        
        for i in range(min_length):
            parts_at_i = [parts[i] for parts in path_parts]
            if len(set(parts_at_i)) == 1:
                common_parts.append(parts_at_i[0])
            else:
                break
        
        if len(common_parts) >= 2:  # At least 2 directories deep
            return str(Path(*common_parts))
        
        return None
    
    def _detect_session_type(self, actions: List[Dict]) -> str:
        """
        Detect the type of session based on actions.
        
        Types:
        - coding: Heavy file editing, git commits
        - research: Lots of browsing, reading docs
        - debugging: Terminal commands, error searches
        - mixed: No clear dominant activity
        """
        # Count indicators for each type
        coding_score = 0
        research_score = 0
        debugging_score = 0
        
        for action in actions:
            source = action['source']
            action_type = action['action_type']
            ctx = action['context']
            
            # Coding indicators
            if source == 'vscode':
                coding_score += 2
            if action_type in ['file_edit', 'file_save', 'git_commit', 'git_push']:
                coding_score += 3
            if action_type in ['file_open', 'file_close']:
                coding_score += 1
            
            # Research indicators
            if source == 'chrome':
                research_score += 1
            if action_type in ['page_visit', 'tab_switch']:
                url = ctx.get('url', '')
                if any(doc_site in url for doc_site in ['docs.', 'documentation', 'github.com', 'stackoverflow', 'mdn']):
                    research_score += 2
            
            # Debugging indicators
            if action_type in ['terminal_command']:
                debugging_score += 1
                cmd = ctx.get('command', '').lower()
                if any(dbg in cmd for dbg in ['debug', 'error', 'log', 'test', 'pytest', 'npm run']):
                    debugging_score += 2
            if 'error' in action_type.lower():
                debugging_score += 3
        
        # Determine session type
        scores = {
            'coding': coding_score,
            'research': research_score,
            'debugging': debugging_score
        }
        
        max_score = max(scores.values())
        if max_score == 0:
            return 'mixed'
        
        # Require significant margin to classify
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if sorted_scores[0][1] >= sorted_scores[1][1] * 1.5:
            return sorted_scores[0][0]
        
        return 'mixed'
    
    def save_session(self, session: Dict) -> int:
        """
        Save a detected session to the database.
        
        Args:
            session: Session metadata dictionary
        
        Returns:
            Session ID
        """
        cursor = self.db.cursor()
        
        import json
        
        cursor.execute("""
            INSERT INTO work_sessions (
                start_time, end_time, duration_seconds, action_count,
                project, session_type, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session['start_time'],
            session['end_time'],
            session['duration_seconds'],
            session['action_count'],
            session['project'],
            session['session_type'],
            json.dumps({
                'source_counts': session['source_counts'],
                'type_counts': session['type_counts'],
                'files': session['files'],
                'apps': session['apps'],
                'urls': session['urls'],
                'commands': session['commands'],
                'action_ids': session['action_ids']
            })
        ))
        
        self.db.commit()
        return cursor.lastrowid
    
    def get_sessions_for_day(self, date: str) -> List[Dict]:
        """
        Get all sessions for a specific day.
        
        Args:
            date: Date string in format 'YYYY-MM-DD'
        
        Returns:
            List of session dictionaries
        """
        from datetime import datetime
        
        dt = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        return self.detect_sessions(start_of_day, end_of_day)

    def create_session(self, project: str, session_type: str, duration_minutes: int, start_time: Optional[float] = None) -> int:
        """
        Manually create a work session.
        
        Args:
            project: Project name
            session_type: Type of session (coding, learning, etc.)
            duration_minutes: Duration in minutes
            start_time: Optional start timestamp (defaults to now - duration)
        
        Returns:
            Session ID
        """
        import time
        import json
        
        if start_time is None:
            end_time = time.time()
            start_time = end_time - (duration_minutes * 60)
        else:
            end_time = start_time + (duration_minutes * 60)
            
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO work_sessions (
                start_time, end_time, duration_seconds, action_count,
                project, session_type, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            start_time,
            end_time,
            duration_minutes * 60,
            0,  # Manual sessions have 0 actions initially
            project,
            session_type,
            json.dumps({
                'source': 'manual',
                'created_at': time.time()
            })
        ))
        
        self.db.commit()
        return cursor.lastrowid


def get_session_detector(db_connection):
    """Get session detector instance."""
    return SessionDetector(db_connection)
