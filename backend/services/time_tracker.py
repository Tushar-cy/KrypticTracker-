import json
"""
Time Tracking Service

Calculates time spent on:
- Apps (VSCode, Chrome, vim, etc.)
- Projects (by git repo or file path)
- Files (individual files)
- Activities (coding, research, debugging)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from pathlib import Path
import json


class TimeTracker:
    """Tracks time spent on various activities, apps, projects, and files."""
    
    def __init__(self, db_connection):
        """Initialize time tracker."""
        self.db = db_connection
    
    def get_daily_breakdown(self, date: str) -> Dict:
        """
        Get complete time breakdown for a specific day.
        
        Args:
            date: Date string in format 'YYYY-MM-DD'
        
        Returns:
            Dictionary with time breakdowns
        """
        from datetime import datetime
        
        dt = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        return {
            'date': date,
            'by_app': self.time_by_app(start_of_day, end_of_day),
            'by_project': self.time_by_project(start_of_day, end_of_day),
            'by_file': self.time_by_file(start_of_day, end_of_day),
            'by_activity': self.time_by_activity_type(start_of_day, end_of_day),
            'total_time': self.total_active_time(start_of_day, end_of_day),
            'context_switches': self.count_context_switches(start_of_day, end_of_day),
            'deep_work_periods': self.detect_deep_work(start_of_day, end_of_day),
        }
    
    def time_by_app(self, start_time: float, end_time: float) -> List[Dict]:
        """Calculate time spent per application."""
        cursor = self.db.cursor()
        
        # Get all actions with app context
        cursor.execute("""
            SELECT timestamp, source, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        app_times = defaultdict(float)
        app_action_counts = defaultdict(int)
        
        last_app = None
        last_timestamp = None
        
        for row in cursor.fetchall():
            timestamp = row[0]
            source = row[1]
            context = json.loads(row[2]) if row[2] else {}
            
            # Determine app
            app = context.get('app') or source or 'unknown'
            
            # If we have a previous app, calculate time spent
            if last_app and last_timestamp:
                time_diff = timestamp - last_timestamp
                # Only count if time diff is reasonable (< 5 minutes)
                if time_diff < 300:
                    app_times[last_app] += time_diff
            
            app_action_counts[app] += 1
            last_app = app
            last_timestamp = timestamp
        
        # Convert to sorted list
        results = []
        for app, seconds in sorted(app_times.items(), key=lambda x: x[1], reverse=True):
            results.append({
                'app': app,
                'seconds': round(seconds, 1),
                'minutes': round(seconds / 60, 1),
                'hours': round(seconds / 3600, 2),
                'action_count': app_action_counts[app],
                'formatted': self._format_duration(seconds)
            })
        
        return results
    
    def time_by_project(self, start_time: float, end_time: float) -> List[Dict]:
        """Calculate time spent per project."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT timestamp, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        project_times = defaultdict(float)
        project_action_counts = defaultdict(int)
        
        last_project = None
        last_timestamp = None
        
        for row in cursor.fetchall():
            timestamp = row[0]
            context = json.loads(row[1]) if row[1] else {}
            
            # Detect project
            project = self._detect_project_from_context(context)
            
            if last_project and last_timestamp:
                time_diff = timestamp - last_timestamp
                if time_diff < 300:  # < 5 minutes
                    project_times[last_project] += time_diff
            
            if project:
                project_action_counts[project] += 1
                last_project = project
                last_timestamp = timestamp
        
        # Convert to sorted list
        results = []
        for project, seconds in sorted(project_times.items(), key=lambda x: x[1], reverse=True):
            if project:  # Skip None/empty projects
                results.append({
                    'project': project,
                    'seconds': round(seconds, 1),
                    'minutes': round(seconds / 60, 1),
                    'hours': round(seconds / 3600, 2),
                    'action_count': project_action_counts[project],
                    'formatted': self._format_duration(seconds)
                })
        
        return results
    
    def time_by_file(self, start_time: float, end_time: float, limit: int = 20) -> List[Dict]:
        """Calculate time spent per file (top N files)."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT timestamp, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            AND (context_json LIKE '%file_path%' OR context_json LIKE '%source_file%')
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        file_times = defaultdict(float)
        file_action_counts = defaultdict(int)
        
        last_file = None
        last_timestamp = None
        
        for row in cursor.fetchall():
            timestamp = row[0]
            context = json.loads(row[1]) if row[1] else {}
            
            # Get file path
            file_path = context.get('file_path') or context.get('source_file')
            
            if last_file and last_timestamp:
                time_diff = timestamp - last_timestamp
                if time_diff < 300:  # < 5 minutes
                    file_times[last_file] += time_diff
            
            if file_path:
                file_action_counts[file_path] += 1
                last_file = file_path
                last_timestamp = timestamp
        
        # Convert to sorted list (top N)
        results = []
        for file_path, seconds in sorted(file_times.items(), key=lambda x: x[1], reverse=True)[:limit]:
            results.append({
                'file': file_path,
                'filename': Path(file_path).name,
                'seconds': round(seconds, 1),
                'minutes': round(seconds / 60, 1),
                'action_count': file_action_counts[file_path],
                'formatted': self._format_duration(seconds)
            })
        
        return results
    
    def time_by_activity_type(self, start_time: float, end_time: float) -> Dict:
        """
        Calculate time by activity type (coding, research, debugging, other).
        """
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT timestamp, source, action_type, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        activity_times = defaultdict(float)
        
        last_activity = None
        last_timestamp = None
        
        for row in cursor.fetchall():
            timestamp = row[0]
            source = row[1]
            action_type = row[2]
            context = json.loads(row[3]) if row[3] else {}
            
            # Classify activity
            activity = self._classify_activity(source, action_type, context)
            
            if last_activity and last_timestamp:
                time_diff = timestamp - last_timestamp
                if time_diff < 300:
                    activity_times[last_activity] += time_diff
            
            last_activity = activity
            last_timestamp = timestamp
        
        return {
            activity: {
                'seconds': round(seconds, 1),
                'minutes': round(seconds / 60, 1),
                'hours': round(seconds / 3600, 2),
                'percentage': 0,  # Will calculate after
                'formatted': self._format_duration(seconds)
            }
            for activity, seconds in activity_times.items()
        }
    
    def total_active_time(self, start_time: float, end_time: float) -> Dict:
        """Calculate total active time (excluding gaps > 5 min)."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT timestamp
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        timestamps = [row[0] for row in cursor.fetchall()]
        
        if len(timestamps) < 2:
            return {'seconds': 0, 'minutes': 0, 'hours': 0, 'formatted': '0m'}
        
        total_seconds = 0
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i-1]
            if gap < 300:  # < 5 minutes
                total_seconds += gap
        
        return {
            'seconds': round(total_seconds, 1),
            'minutes': round(total_seconds / 60, 1),
            'hours': round(total_seconds / 3600, 2),
            'formatted': self._format_duration(total_seconds)
        }
    
    def count_context_switches(self, start_time: float, end_time: float) -> int:
        """Count number of context switches (app/project changes)."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT timestamp, source, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        switches = 0
        last_context = None
        
        for row in cursor.fetchall():
            context = json.loads(row[2]) if row[2] else {}
            
            # Define context as (app, project)
            app = context.get('app') or row[1]
            project = self._detect_project_from_context(context)
            current_context = (app, project)
            
            if last_context and current_context != last_context:
                switches += 1
            
            last_context = current_context
        
        return switches
    
    def detect_deep_work(self, start_time: float, end_time: float, min_duration_minutes: int = 25) -> List[Dict]:
        """
        Detect deep work periods (sustained focus on same project/activity).
        
        Args:
            start_time: Start timestamp
            end_time: End timestamp
            min_duration_minutes: Minimum duration to count as deep work
        
        Returns:
            List of deep work periods
        """
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT timestamp, source, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        deep_work_periods = []
        current_period_start = None
        current_project = None
        last_timestamp = None
        
        for row in cursor.fetchall():
            timestamp = row[0]
            context = json.loads(row[2]) if row[2] else {}
            project = self._detect_project_from_context(context)
            
            if current_project is None:
                # Start new period
                current_period_start = timestamp
                current_project = project
                last_timestamp = timestamp
            elif project != current_project or (timestamp - last_timestamp > 300):
                # Project changed or gap too large - end current period
                if current_period_start and last_timestamp:
                    duration = last_timestamp - current_period_start
                    if duration >= min_duration_minutes * 60:
                        deep_work_periods.append({
                            'start_time': current_period_start,
                            'end_time': last_timestamp,
                            'duration_minutes': round(duration / 60, 1),
                            'project': current_project,
                            'formatted': self._format_duration(duration)
                        })
                # Start new period
                current_period_start = timestamp
                current_project = project
            
            last_timestamp = timestamp
        
        # Don't forget last period
        if current_period_start and last_timestamp:
            duration = last_timestamp - current_period_start
            if duration >= min_duration_minutes * 60:
                deep_work_periods.append({
                    'start_time': current_period_start,
                    'end_time': last_timestamp,
                    'duration_minutes': round(duration / 60, 1),
                    'project': current_project,
                    'formatted': self._format_duration(duration)
                })
        
        return deep_work_periods
    
    def _detect_project_from_context(self, context: Dict) -> Optional[str]:
        """Detect project from action context."""
        # Check git repo
        if 'git_repo' in context and context['git_repo']:
            return Path(context['git_repo']).name
        if 'repo_path' in context and context['repo_path']:
            return Path(context['repo_path']).name
        
        # Check working directory
        if 'working_directory' in context:
            return Path(context['working_directory']).name
        
        # Check file path
        if 'file_path' in context:
            # Extract project from path (e.g., ~/projects/myproject/file.py -> myproject)
            path_parts = Path(context['file_path']).parts
            if len(path_parts) > 2:
                return path_parts[-2]  # Parent directory
        
        return None
    
    def _classify_activity(self, source: str, action_type: str, context: Dict) -> str:
        """Classify action into activity type."""
        # Coding
        if source == 'vscode' or action_type in ['file_edit', 'file_save', 'git_commit']:
            return 'coding'
        
        # Research/browsing
        if source == 'chrome' or action_type in ['page_visit', 'tab_switch']:
            url = context.get('url', '')
            if any(doc in url for doc in ['docs.', 'documentation', 'stackoverflow', 'github.com']):
                return 'research'
            return 'browsing'
        
        # Terminal/debugging
        if action_type in ['terminal_command', 'npm_history_command', 'pip_history_command']:
            return 'terminal'
        
        return 'other'
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"


def get_time_tracker(db_connection):
    """Get time tracker instance."""
    return TimeTracker(db_connection)
