"""
Distraction Tracker

Tracks and analyzes distractions to quantify their impact on productivity.
Categorizes distractions and calculates time lost.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter


class DistractionTracker:
    """Tracks and analyzes distractions."""
    
    # Known distraction sources
    SOCIAL_MEDIA_APPS = {
        'twitter', 'reddit', 'instagram', 'facebook', 'tiktok',
        'linkedin', 'snapchat', 'pinterest'
    }
    
    SOCIAL_MEDIA_DOMAINS = {
        'twitter.com', 'reddit.com', 'instagram.com', 'facebook.com',
        'tiktok.com', 'linkedin.com', 'youtube.com', 'twitch.tv'
    }
    
    MESSAGE_APPS = {
        'slack', 'discord', 'telegram', 'whatsapp', 'messenger',
        'teams', 'skype'
    }
    
    ENTERTAINMENT_DOMAINS = {
        'netflix.com', 'youtube.com', 'twitch.tv', 'spotify.com',
        'primevideo.com', 'disneyplus.com'
    }
    
    # Context switch penalty (minutes lost per switch)
    CONTEXT_SWITCH_PENALTY = 23  # Research shows ~23 min to refocus
    
    def __init__(self, db_connection):
        """Initialize distraction tracker."""
        self.db = db_connection
    
    def track_distractions(self, start_time: float, end_time: float) -> Dict:
        """
        Track all distractions in time period.
        
        Returns dict with:
        - total_distraction_time
        - by_category breakdown
        - context_switch_count
        - distraction_events list
        """
        cursor = self.db.cursor()
        
        # Get all actions in timeframe
        cursor.execute("""
            SELECT timestamp, source, action_type, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        import json
        actions = []
        for row in cursor.fetchall():
            actions.append({
                'timestamp': row[0],
                'source': row[1],
                'action_type': row[2],
                'context': json.loads(row[3]) if row[3] else {}
            })
        
        # Analyze distractions
        distractions_by_category = defaultdict(float)  # minutes
        distraction_events = []
        context_switches = 0
        last_app = None
        last_project = None
        
        for i, action in enumerate(actions):
            # Check if this action is a distraction
            category = self._categorize_distraction(action)
            
            if category:
                # Calculate time spent (estimate based on next action)
                if i < len(actions) - 1:
                    time_spent = (actions[i+1]['timestamp'] - action['timestamp']) / 60
                    time_spent = min(time_spent, 30)  # Cap at 30 min per event
                else:
                    time_spent = 5  # Default 5 min for last action
                
                distractions_by_category[category] += time_spent
                
                distraction_events.append({
                    'timestamp': action['timestamp'],
                    'category': category,
                    'source': action['source'],
                    'duration_minutes': round(time_spent, 1),
                    'details': self._get_distraction_details(action)
                })
            
            # Track context switches
            current_app = action['source']
            current_project = action['context'].get('project') or action['context'].get('working_directory')
            
            if last_app and current_app != last_app:
                # Check if it's a meaningful switch (not same project)
                if last_project and current_project and last_project != current_project:
                    context_switches += 1
            
            last_app = current_app
            last_project = current_project
        
        # Calculate total distraction time
        total_distraction_time = sum(distractions_by_category.values())
        
        return {
            'total_distraction_minutes': round(total_distraction_time, 1),
            'total_distraction_formatted': self._format_duration(total_distraction_time),
            'by_category': dict(distractions_by_category),
            'context_switches': context_switches,
            'estimated_switch_cost_minutes': context_switches * self.CONTEXT_SWITCH_PENALTY,
            'distraction_events': distraction_events[:50],  # Limit to 50 most recent
            'top_distractions': self._get_top_distractions(distraction_events, 5)
        }
    
    def _categorize_distraction(self, action: Dict) -> Optional[str]:
        """
        Categorize an action as a distraction type or None.
        
        Returns: 'social_media', 'messaging', 'entertainment', 'browsing', or None
        """
        source = action['source'].lower()
        action_type = action['action_type']
        context = action['context']
        
        # Check source/app
        if source in self.SOCIAL_MEDIA_APPS:
            return 'social_media'
        
        if source in self.MESSAGE_APPS:
            return 'messaging'
        
        # Check URLs for browser activity
        if action_type in ['page_visit', 'tab_switch']:
            url = context.get('url', '').lower()
            domain = context.get('domain', '').lower()
            
            # Social media
            if any(d in url or d in domain for d in self.SOCIAL_MEDIA_DOMAINS):
                return 'social_media'
           
            # Entertainment
            if any(d in url or d in domain for d in self.ENTERTAINMENT_DOMAINS):
                return 'entertainment'
            
            # Non-work browsing (heuristic: non-dev sites during work hours)
            if self._is_work_hours(action['timestamp']):
                if not self._is_work_related_url(url):
                    return 'browsing'
        
        return None
    
    def _is_work_hours(self, timestamp: float) -> bool:
        """Check if timestamp is during typical work hours (9am-6pm)."""
        dt = datetime.fromtimestamp(timestamp)
        return 9 <= dt.hour < 18 and dt.weekday() < 5  # Mon-Fri
    
    def _is_work_related_url(self, url: str) -> bool:
        """Heuristic to determine if URL is work-related."""
        work_keywords = [
            'github', 'stackoverflow', 'docs.', 'documentation',
            'api', 'developer', 'mdn', 'w3schools', 'pypi',
            'npmjs', 'localhost', '127.0.0.1'
        ]
        
        return any(keyword in url.lower() for keyword in work_keywords)
    
    def _get_distraction_details(self, action: Dict) -> str:
        """Get human-readable details about a distraction."""
        context = action['context']
        
        if 'url' in context:
            return context.get('title', context.get('url', ''))[:50]
        elif 'app' in context:
            return context['app']
        
        return action['source']
    
    def _get_top_distractions(self, events: List[Dict], limit: int = 5) -> List[Dict]:
        """Get top distractions by frequency and time."""
        # Group by details
        distraction_groups = defaultdict(lambda: {'count': 0, 'total_time': 0, 'category': ''})
        
        for event in events:
            key = event['details']
            distraction_groups[key]['count'] += 1
            distraction_groups[key]['total_time'] += event['duration_minutes']
            distraction_groups[key]['category'] = event['category']
        
        # Sort by total time
        sorted_distractions = sorted(
            distraction_groups.items(),
            key=lambda x: x[1]['total_time'],
            reverse=True
        )
        
        return [
            {
                'name': name,
                'count': data['count'],
                'total_minutes': round(data['total_time'], 1),
                'category': data['category']
            }
            for name, data in sorted_distractions[:limit]
        ]
    
    def _format_duration(self, minutes: float) -> str:
        """Format minutes as 'Xh Ym' or 'Xm'."""
        if minutes < 60:
            return f"{int(minutes)}m"
        
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}m"
    
    def calculate_distraction_percentage(self, start_time: float, end_time: float) -> float:
        """
        Calculate percentage of work time spent on distractions.
        
        Returns: Percentage (0-100)
        """
        from backend.services.time_tracker import get_time_tracker
        
        tracker = get_time_tracker(self.db)
        
        # Get total work time
        date_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')
        try:
            breakdown = tracker.get_daily_breakdown(date_str)
            total_minutes = breakdown['total_time'].get('minutes', 0)
        except:
            total_minutes = 0
        
        if total_minutes == 0:
            return 0
        
        # Get distraction time
        distraction_data = self.track_distractions(start_time, end_time)
        distraction_minutes = distraction_data['total_distraction_minutes']
        
        return round((distraction_minutes / total_minutes) * 100, 1)
    
    def get_focus_vs_distracted_breakdown(self, start_time: float, end_time: float) -> Dict:
        """
        Get breakdown of focused vs distracted time.
        
        Returns dict with:
        - focused_time
        - distracted_time
        - context_switch_overhead
        - unknown_time
        """
        from backend.services.time_tracker import get_time_tracker
        
        tracker = get_time_tracker(self.db)
        date_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d')
        
        try:
            breakdown = tracker.get_daily_breakdown(date_str)
            total_minutes = breakdown['total_time'].get('minutes', 0)
            deep_work = sum(p['duration_minutes'] for p in breakdown['deep_work_periods'])
        except:
            total_minutes = 0
            deep_work = 0
        
        distraction_data = self.track_distractions(start_time, end_time)
        distracted_minutes = distraction_data['total_distraction_minutes']
        switch_overhead = (distraction_data['context_switches'] * self.CONTEXT_SWITCH_PENALTY) / 60  # hours
        
        # Focused time = deep work + (total - distractions - deep work) * 0.6
        # (assuming 60% of non-deep-work time is still focused)
        other_time = max(0, total_minutes - deep_work - distracted_minutes)
        focused_time = deep_work + (other_time * 0.6)
        
        unknown_time = max(0, total_minutes - focused_time - distracted_minutes)
        
        return {
            'focused_minutes': round(focused_time, 1),
            'focused_formatted': self._format_duration(focused_time),
            'distracted_minutes': round(distracted_minutes, 1),
            'distracted_formatted': self._format_duration(distracted_minutes),
            'switch_overhead_hours': round(switch_overhead, 1),
            'unknown_minutes': round(unknown_time, 1),
            'focus_percentage': round((focused_time / total_minutes * 100), 1) if total_minutes > 0 else 0
        }


def get_distraction_tracker(db_connection):
    """Get distraction tracker instance."""
    return DistractionTracker(db_connection)
