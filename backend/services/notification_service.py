"""
Smart Notification Service

Provides timely notifications for breaks, goal misalignment, focus sessions, and reviews.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json


class NotificationService:
    """Manages smart productivity notifications."""
    
    def __init__(self, db_connection):
        """Initialize notification service."""
        self.db = db_connection
        self._create_notification_table()
    
    def _create_notification_table(self):
        """Create notification log table if it doesn't exist."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                sent_at REAL DEFAULT (strftime('%s', 'now')),
                acknowledged BOOLEAN DEFAULT 0,
                metadata TEXT
            )
        """)
        
        self.db.commit()
    
    def check_break_needed(self) -> Dict:
        """
        Check if a break is needed based on continuous work time.
        
        Returns:
            {needed, worked_minutes, suggested_break, message}
        """
        cursor = self.db.cursor()
        
        # Get actions from the last 3 hours
        now = datetime.now().timestamp()
        three_hours_ago = (datetime.now() - timedelta(hours=3)).timestamp()
        
        cursor.execute("""
            SELECT timestamp FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (three_hours_ago, now))
        
        timestamps = [row[0] for row in cursor.fetchall()]
        
        if not timestamps:
            return {
                'needed': False,
                'worked_minutes': 0,
                'suggested_break': 0,
                'message': 'No recent activity'
            }
        
        # Find the longest continuous work period
        max_continuous = 0
        current_continuous = 0
        last_timestamp = None
        
        for ts in timestamps:
            if last_timestamp:
                gap = (ts - last_timestamp) / 60  # minutes
                
                if gap < 10:  # Continuous work
                    current_continuous += gap
                else:  # Break detected
                    max_continuous = max(max_continuous, current_continuous)
                    current_continuous = 0
            
            last_timestamp = ts
        
        max_continuous = max(max_continuous, current_continuous)
        
        # Determine if break is needed
        if max_continuous >= 120:  # 2 hours
            return {
                'needed': True,
                'worked_minutes': int(max_continuous),
                'suggested_break': 15,
                'message': f'⚠️ You\'ve worked for {int(max_continuous)} minutes straight. Time for a 15-min break!',
                'urgency': 'high'
            }
        elif max_continuous >= 90:  # 1.5 hours
            return {
                'needed': True,
                'worked_minutes': int(max_continuous),
                'suggested_break': 10,
                'message': f'💡 {int(max_continuous)} minutes of work. Consider a quick 10-min break.',
                'urgency': 'medium'
            }
        else:
            return {
                'needed': False,
                'worked_minutes': int(max_continuous),
                'suggested_break': 0,
                'message': 'Keep going! You\'re maintaining a good pace.',
                'urgency': 'none'
            }
    
    def check_goal_misalignment(self) -> Dict:
        """
        Check if current work is misaligned with goals.
        
        Returns:
            {misaligned, current_pct, top_goal, message}
        """
        from backend.services.goal_service import get_goal_service
        
        try:
            goals = get_goal_service(self.db)
            
            # Check today's alignment
            today = datetime.now().strftime('%Y-%m-%d')
            alignment = goals.check_goal_alignment(today)
            
            alignment_pct = alignment.get('overall_alignment_percentage', 0)
            
            if alignment_pct < 40:
                active_goals = goals.get_active_goals()
                top_goal = active_goals[0]['goal_text'] if active_goals else 'your goals'
                
                return {
                    'misaligned': True,
                    'current_pct': alignment_pct,
                    'top_goal': top_goal,
                    'message': f'⚠️ Only {alignment_pct:.0f}% aligned with "{top_goal}". Refocus?',
                    'urgency': 'high'
                }
            elif alignment_pct < 60:
                return {
                    'misaligned': True,
                    'current_pct': alignment_pct,
                    'top_goal': None,
                    'message': f'💡 {alignment_pct:.0f}% goal alignment. Room for improvement.',
                    'urgency': 'medium'
                }
            else:
                return {
                    'misaligned': False,
                    'current_pct': alignment_pct,
                    'top_goal': None,
                    'message': f'✅ Great! {alignment_pct:.0f}% aligned with your goals.',
                    'urgency': 'none'
                }
        except:
            return {
                'misaligned': False,
                'current_pct': 0,
                'top_goal': None,
                'message': 'No active goals set',
                'urgency': 'none'
            }
    
    def suggest_focus_session(self) -> Dict:
        """
        Recommend starting a focus session during peak hours.
        
        Returns:
            {suggested, reason, duration, message}
        """
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        peak_hours = analyzer.get_peak_hours(days=7)
        
        if not peak_hours:
            return {
                'suggested': False,
                'reason': 'Insufficient data',
                'duration': 0,
                'message': 'Build more history to get recommendations'
            }
        
        # Check if we're in a peak hour now
        current_hour = datetime.now().hour
        
        for peak_time, score in peak_hours[:3]:
            peak_hour = int(peak_time.split('-')[0].split(':')[0])
            
            if peak_hour == current_hour:
                return {
                    'suggested': True,
                    'reason': f'Peak productivity hour (score: {score:.0f})',
                    'duration': 50,  # Pomodoro-style
                    'message': f'🔥 Perfect time for a focus session! This is your peak hour.',
                    'urgency': 'high'
                }
            elif peak_hour == current_hour + 1:
                return {
                    'suggested': True,
                    'reason': f'Approaching peak hour at {peak_time}',
                    'duration': 50,
                    'message': f'💡 Get ready - your peak hour starts at {peak_time}',
                    'urgency': 'medium'
                }
        
        # Not a peak time
        next_peak = peak_hours[0][0]
        return {
            'suggested': False,
            'reason': 'Not currently a peak time',
            'duration': 0,
            'message': f'Your next peak hour is at {next_peak}',
            'urgency': 'low'
        }
    
    def weekly_review_reminder(self) -> Dict:
        """
        Check if weekly review is due.
        
        Returns:
            {due, last_review_date, message}
        """
        cursor = self.db.cursor()
        
        # Check for last weekly review notification
        cursor.execute("""
            SELECT sent_at FROM notification_log
            WHERE type = 'weekly_review'
            ORDER BY sent_at DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        
        if row:
            last_review = datetime.fromtimestamp(row[0])
            days_since = (datetime.now() - last_review).days
            
            if days_since >= 7:
                return {
                    'due': True,
                    'last_review_date': last_review.strftime('%Y-%m-%d'),
                    'days_since': days_since,
                    'message': f'📊 Weekly review time! Last review was {days_since} days ago.',
                    'urgency': 'high'
                }
            else:
                return {
                    'due': False,
                    'last_review_date': last_review.strftime('%Y-%m-%d'),
                    'days_since': days_since,
                    'message': f'Next review in {7 - days_since} days',
                    'urgency': 'none'
                }
        else:
            # No review yet
            return {
                'due': True,
                'last_review_date': None,
                'days_since': 999,
                'message': '📊 Time for your first weekly review!',
                'urgency': 'high'
            }
    
    def get_all_pending_notifications(self) -> List[Dict]:
        """
        Get all pending notifications that should be shown.
        
        Returns:
            List of notification dicts
        """
        notifications = []
        
        # Check break
        break_check = self.check_break_needed()
        if break_check['needed']:
            notifications.append({
                'type': 'break',
                'urgency': break_check['urgency'],
                'message': break_check['message'],
                'data': break_check
            })
        
        # Check goal alignment
        goal_check = self.check_goal_misalignment()
        if goal_check['misaligned']:
            notifications.append({
                'type': 'goal_alignment',
                'urgency': goal_check['urgency'],
                'message': goal_check['message'],
                'data': goal_check
            })
        
        # Check focus session
        focus_check = self.suggest_focus_session()
        if focus_check['suggested']:
            notifications.append({
                'type': 'focus_session',
                'urgency': focus_check['urgency'],
                'message': focus_check['message'],
                'data': focus_check
            })
        
        # Check weekly review
        review_check = self.weekly_review_reminder()
        if review_check['due']:
            notifications.append({
                'type': 'weekly_review',
                'urgency': review_check['urgency'],
                'message': review_check['message'],
                'data': review_check
            })
        
        # Sort by urgency
        urgency_order = {'high': 0, 'medium': 1, 'low': 2, 'none': 3}
        notifications.sort(key=lambda x: urgency_order.get(x['urgency'], 3))
        
        return notifications
    
    def log_notification(self, notification_type: str, message: str, metadata: Optional[Dict] = None):
        """
        Log a sent notification.
        
        Args:
            notification_type: Type of notification
            message: Notification message
            metadata: Optional additional data
        """
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO notification_log (type, message, metadata)
            VALUES (?, ?, ?)
        """, (
            notification_type,
            message,
            json.dumps(metadata) if metadata else None
        ))
        
        self.db.commit()
    
    def acknowledge_notification(self, notification_id: int):
        """Mark a notification as acknowledged."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            UPDATE notification_log
            SET acknowledged = 1
            WHERE id = ?
        """, (notification_id,))
        
        self.db.commit()


def get_notification_service(db_connection):
    """Get notification service instance."""
    return NotificationService(db_connection)
