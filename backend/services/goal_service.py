"""
Goal Service

Manages user goals and tracks progress toward them.
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import time


class GoalService:
    """Service for managing user goals and tracking alignment."""
    
    def __init__(self, db_connection):
        """Initialize goal service."""
        self.db = db_connection
    
    def create_goal(self, goal_text: str, keywords: List[str],
                   target_date: Optional[float] = None,
                   category: str = 'general') -> int:
        """
        Create a new user goal.
        
        Args:
            goal_text: Description of the goal
            keywords: List of keywords to match actions against
            target_date: Optional target completion date (unix timestamp)
            category: Goal category
        
        Returns:
            Goal ID
        """
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO user_goals (
                goal_text, created_at, target_date, keywords, category, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            goal_text,
            time.time(),
            target_date,
            json.dumps(keywords),
            category,
            json.dumps({})
        ))
        
        self.db.commit()
        return cursor.lastrowid
    
    def get_active_goals(self) -> List[Dict]:
        """Get all active goals."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT id, goal_text, created_at, target_date, keywords, category, metadata
            FROM user_goals
            WHERE status = 'active'
            ORDER BY created_at DESC
        """)
        
        goals = []
        for row in cursor.fetchall():
            goals.append({
                'id': row[0],
                'goal_text': row[1],
                'created_at': row[2],
                'target_date': row[3],
                'keywords': json.loads(row[4]) if row[4] else [],
                'category': row[5],
                'metadata': json.loads(row[6]) if row[6] else {}
            })
        
        return goals
    
    def update_goal_status(self, goal_id: int, status: str):
        """Update goal status (active, completed, abandoned)."""
        cursor = self.db.cursor()
        cursor.execute("UPDATE user_goals SET status = ? WHERE id = ?", (status, goal_id))
        self.db.commit()
    
    def check_alignment(self, goal_id: int, start_time: float, end_time: float) -> Dict:
        """
        Check how well actions align with a goal.
        
        Args:
            goal_id: Goal ID
            start_time: Start timestamp
            end_time: End timestamp
        
        Returns:
            Alignment statistics
        """
        # Get goal keywords
        cursor = self.db.cursor()
        cursor.execute("SELECT keywords FROM user_goals WHERE id = ?", (goal_id,))
        result = cursor.fetchone()
        
        if not result:
            return {'error': 'Goal not found'}
        
        keywords = json.loads(result[0]) if result[0] else []
        
        if not keywords:
            return {'error': 'No keywords defined for goal'}
        
        # Get all actions in timeframe
        cursor.execute("""
            SELECT id, timestamp, source, action_type, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
        """, (start_time, end_time))
        
        total_actions = 0
        relevant_actions = 0
        relevant_time = 0
        last_relevant_timestamp = None
        
        for row in cursor.fetchall():
            total_actions += 1
            action_id = row[0]
            timestamp = row[1]
            source = row[2]
            action_type = row[3]
            context = json.loads(row[4]) if row[4] else {}
            
            # Check if action is relevant to goal
            if self._is_action_relevant(action_type, context, keywords):
                relevant_actions += 1
                
                # Calculate time spent
                if last_relevant_timestamp:
                    time_diff = timestamp - last_relevant_timestamp
                    if time_diff < 300:  # < 5 minutes
                        relevant_time += time_diff
                
                last_relevant_timestamp = timestamp
        
        # Calculate alignment percentage
        alignment_percentage = (relevant_actions / total_actions * 100) if total_actions > 0 else 0
        
        return {
            'goal_id': goal_id,
            'total_actions': total_actions,
            'relevant_actions': relevant_actions,
            'alignment_percentage': round(alignment_percentage, 1),
            'time_spent_seconds': round(relevant_time, 1),
            'time_spent_minutes': round(relevant_time / 60, 1),
            'time_spent_hours': round(relevant_time / 3600, 2)
        }
    
    def _is_action_relevant(self, action_type: str, context: Dict, keywords: List[str]) -> bool:
        """Check if an action is relevant to goal keywords."""
        # Convert keywords to lowercase for case-insensitive matching
        keywords_lower = [k.lower() for k in keywords]
        
        # Check action type
        if any(kw in action_type.lower() for kw in keywords_lower):
            return True
        
        # Check context fields
        searchable_fields = [
            'command', 'full_command', 'url', 'title', 'file_path',
            'source_file', 'app', 'git_repo', 'repo_path', 'package_name'
        ]
        
        for field in searchable_fields:
            if field in context and context[field]:
                value_str = str(context[field]).lower()
                if any(kw in value_str for kw in keywords_lower):
                    return True
        
        return False
    
    def track_daily_progress(self, goal_id: int, date: str):
        """
        Track daily progress for a goal.
        
        Args:
            goal_id: Goal ID
            date: Date string in YYYY-MM-DD format
        """
        # Convert date to timestamp range
        dt = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        # Get alignment stats
        stats = self.check_alignment(goal_id, start_of_day, end_of_day)
        
        if 'error' in stats:
            return
        
        # Save to goal_progress table
        cursor = self.db.cursor()
        
        # Check if entry exists for today
        cursor.execute("""
            SELECT id FROM goal_progress
            WHERE goal_id = ? AND date = ?
        """, (goal_id, date))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            cursor.execute("""
                UPDATE goal_progress
                SET relevant_actions = ?, total_actions = ?, time_spent_seconds = ?
                WHERE id = ?
            """, (
                stats['relevant_actions'],
                stats['total_actions'],
                stats['time_spent_seconds'],
                existing[0]
            ))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO goal_progress (
                    goal_id, date, relevant_actions, total_actions, time_spent_seconds
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                goal_id,
                date,
                stats['relevant_actions'],
                stats['total_actions'],
                stats['time_spent_seconds']
            ))
        
        self.db.commit()
    
    def get_goal_progress_history(self, goal_id: int, days: int = 7) -> List[Dict]:
        """Get goal progress for last N days."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT date, relevant_actions, total_actions, time_spent_seconds
            FROM goal_progress
            WHERE goal_id = ?
            ORDER BY date DESC
            LIMIT ?
        """, (goal_id, days))
        
        history = []
        for row in cursor.fetchall():
            total = row[2]
            relevant = row[1]
            alignment = (relevant / total * 100) if total > 0 else 0
            
            history.append({
                'date': row[0],
                'relevant_actions': row[1],
                'total_actions': row[2],
                'time_spent_seconds': row[3],
                'time_spent_hours': round(row[3] / 3600, 2),
                'alignment_percentage': round(alignment, 1)
            })
        
        return history
    
    def generate_feedback(self, goal_id: int, timeframe: str = 'week') -> str:
        """
        Generate feedback message about goal alignment.
        
        Args:
            goal_id: Goal ID
            timeframe: 'day', 'week', or 'month'
        
        Returns:
            Feedback message
        """
        # Get goal
        cursor = self.db.cursor()
        cursor.execute("SELECT goal_text FROM user_goals WHERE id = ?", (goal_id,))
        result = cursor.fetchone()
        
        if not result:
            return "Goal not found"
        
        goal_text = result[0]
        
        # Calculate time range
        now = time.time()
        if timeframe == 'day':
            start_time = now - (24 * 3600)
        elif timeframe == 'week':
            start_time = now - (7 * 24 * 3600)
        else:  # month
            start_time = now - (30 * 24 * 3600)
        
        # Get alignment stats
        stats = self.check_alignment(goal_id, start_time, now)
        
        if 'error' in stats:
            return f"Could not calculate alignment: {stats['error']}"
        
        # Generate feedback
        alignment = stats['alignment_percentage']
        hours = stats['time_spent_hours']
        
        if alignment >= 70:
            emoji = "✅"
            message = f"{emoji} Great! {alignment:.0f}% of your {timeframe} was aligned with '{goal_text}' ({hours:.1f}h total)"
        elif alignment >= 40:
            emoji = "⚠️"
            message = f"{emoji} Moderate progress: {alignment:.0f}% aligned with '{goal_text}' ({hours:.1f}h). Try to increase focus."
        else:
            emoji = "❌"
            message = f"{emoji} Low alignment: Only {alignment:.0f}% aligned with '{goal_text}' ({hours:.1f}h). You may be off track."
        
        return message


def get_goal_service(db_connection):
    """Get goal service instance."""
    return GoalService(db_connection)
