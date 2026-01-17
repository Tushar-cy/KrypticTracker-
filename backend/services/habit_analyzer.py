"""
Habit Analyzer Service

Tracks daily habits, detects streaks, and calculates consistency scores.
Automatically tracks built-in productivity habits.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json


class HabitAnalyzer:
    """Analyzes and tracks user habits."""
    
    # Built-in habits that are tracked automatically
    BUILTIN_HABITS = {
        'coding_2h': {
            'name': 'coding_2h',
            'description': '2+ hours of coding per day',
            'target_value': 120,  # minutes
            'unit': 'minutes',
            'keywords': ['code', 'git', 'vscode', 'python', 'javascript']
        },
        'learning_1h': {
            'name': 'learning_1h',
            'description': '1+ hour on educational content',
            'target_value': 60,
            'unit': 'minutes',
            'keywords': ['course', 'tutorial', 'docs', 'documentation', 'learning']
        },
        'deep_work_25m': {
            'name': 'deep_work_25m',
            'description': 'At least one 25+ min deep work session',
            'target_value': 1,
            'unit': 'sessions',
            'keywords': []
        },
        'goal_aligned_50pct': {
            'name': 'goal_aligned_50pct',
            'description': '50%+ time aligned with goals',
            'target_value': 50,
            'unit': 'percent',
            'keywords': []
        },
        'minimal_distractions': {
            'name': 'minimal_distractions',
            'description': '<30 min total distraction time',
            'target_value': 30,
            'unit': 'minutes',
            'keywords': []
        }
    }
    
    def __init__(self, db_connection):
        """Initialize habit analyzer."""
        self.db = db_connection
        self._ensure_builtin_habits()
    
    def _ensure_builtin_habits(self):
        """Ensure built-in habits are in database."""
        cursor = self.db.cursor()
        
        for habit_id, habit in self.BUILTIN_HABITS.items():
            cursor.execute("""
                INSERT OR IGNORE INTO user_habits (name, description, target_value, unit, keywords)
                VALUES (?, ?, ?, ?, ?)
            """, (
                habit['name'],
                habit['description'],
                habit['target_value'],
                habit['unit'],
                json.dumps(habit['keywords'])
            ))
        
        self.db.commit()
    
        self.db.commit()
    
    def create_habit(self, name: str, description: str, target_value: int, unit: str, keywords: List[str] = None):
        """
        Create a new custom habit.
        
        Args:
            name: Unique name/slug for the habit
            description: Display description
            target_value: Target value to achieve
            unit: Unit of measurement (minutes, count, percent)
            keywords: Optional keywords for auto-tracking
        """
        cursor = self.db.cursor()
        
        cursor.execute("""
            INSERT INTO user_habits (name, description, target_value, unit, keywords, active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (
            name,
            description,
            target_value,
            unit,
            json.dumps(keywords or [])
        ))
        
        self.db.commit()
        return cursor.lastrowid

    def track_habit(self, habit_name: str, date: str, completed: bool, value: Optional[float] = None):
        """
        Track habit completion for a specific date.
        
        Args:
            habit_name: Name of the habit
            date: Date in YYYY-MM-DD format
            completed: Whether habit was completed
            value: Optional numeric value (for quantifiable habits)
        
        Returns:
            dict with completion status and current streak
        """
        cursor = self.db.cursor()
        
        # Insert or update
        cursor.execute("""
            INSERT INTO habit_tracking (habit_name, date, completed, value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(habit_name, date) DO UPDATE SET
                completed = excluded.completed,
                value = excluded.value
        """, (habit_name, date, completed, value))
        
        self.db.commit()
        
        # Get current streak
        streak = self.get_current_streak(habit_name)
        
        return {
            'habit_name': habit_name,
            'date': date,
            'completed': completed,
            'value': value,
            'current_streak': streak
        }
    
    def get_current_streak(self, habit_name: str) -> int:
        """
        Get current consecutive days streak for a habit.
        
        Returns:
            Number of consecutive days (including today if completed)
        """
        cursor = self.db.cursor()
        
        # Get all completions ordered by date descending
        cursor.execute("""
            SELECT date, completed
            FROM habit_tracking
            WHERE habit_name = ?
            ORDER BY date DESC
        """, (habit_name,))
        
        rows = cursor.fetchall()
        if not rows:
            return 0
        
        streak = 0
        expected_date = datetime.now().date()
        
        for row in rows:
            date = datetime.strptime(row[0], '%Y-%m-%d').date()
            completed = bool(row[1])
            
            if date == expected_date and completed:
                streak += 1
                expected_date -= timedelta(days=1)
            elif date < expected_date:
                # Gap in the streak
                break
        
        return streak
    
    def get_longest_streak(self, habit_name: str) -> Dict:
        """
        Get the longest streak ever for a habit.
        
        Returns:
            dict with streak length, start_date, and end_date
        """
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT date, completed
            FROM habit_tracking
            WHERE habit_name = ?
            ORDER BY date ASC
        """, (habit_name,))
        
        rows = cursor.fetchall()
        if not rows:
            return {'streak': 0, 'start_date': None, 'end_date': None}
        
        max_streak = 0
        max_start = None
        max_end = None
        
        current_streak = 0
        current_start = None
        last_date = None
        
        for row in rows:
            date_str = row[0]
            completed = bool(row[1])
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            if completed:
                if current_streak == 0:
                    current_start = date_str
                    current_streak = 1
                elif last_date and (date - last_date).days == 1:
                    current_streak += 1
                else:
                    # Gap - check if this was the longest
                    if current_streak > max_streak:
                        max_streak = current_streak
                        max_start = current_start
                        max_end = last_date.strftime('%Y-%m-%d')
                    current_start = date_str
                    current_streak = 1
                
                last_date = date
            else:
                # Non-completion breaks streak
                if current_streak > max_streak:
                    max_streak = current_streak
                    max_start = current_start
                    max_end = last_date.strftime('%Y-%m-%d') if last_date else None
                current_streak = 0
                current_start = None
        
        # Check final streak
        if current_streak > max_streak:
            max_streak = current_streak
            max_start = current_start
            max_end = last_date.strftime('%Y-%m-%d') if last_date else None
        
        return {
            'streak': max_streak,
            'start_date': max_start,
            'end_date': max_end
        }
    
    def get_consistency_score(self, habit_name: str, days: int = 30) -> float:
        """
        Calculate consistency percentage over a period.
        
        Args:
            habit_name: Name of habit
            days: Number of days to analyze
        
        Returns:
            Percentage (0-100) of days completed
        """
        cursor = self.db.cursor()
        
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT COUNT(*) as total, SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed
            FROM habit_tracking
            WHERE habit_name = ? AND date >= ? AND date <= ?
        """, (habit_name, start_date, end_date))
        
        row = cursor.fetchone()
        total = row[0] or 0
        completed = row[1] or 0
        
        if total == 0:
            return 0.0
        
        return (completed / days) * 100  # Out of total days, not just tracked days
    
    def auto_track_habits(self, date: str):
        """
        Automatically track built-in habits for a given date.
        Uses data from time tracker, session detector, and distraction tracker.
        
        Args:
            date: Date in YYYY-MM-DD format
        """
        from backend.services.time_tracker import get_time_tracker
        from backend.services.session_detector import get_session_detector
        from backend.services.distraction_tracker import get_distraction_tracker
        from backend.services.goal_service import get_goal_service
        
        tracker = get_time_tracker(self.db)
        sessions = get_session_detector(self.db)
        distraction = get_distraction_tracker(self.db)
        goals = get_goal_service(self.db)
        
        # Get timestamps for the day
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        start_time = date_obj.replace(hour=0, minute=0, second=0).timestamp()
        end_time = date_obj.replace(hour=23, minute=59, second=59).timestamp()
        
        try:
            # 1. Coding 2h
            breakdown = tracker.get_daily_breakdown(date)
            coding_time = 0
            for app, data in breakdown.get('by_source', {}).items():
                if any(kw in app.lower() for kw in ['code', 'vscode', 'vim', 'git']):
                    coding_time += data.get('minutes', 0)
            
            self.track_habit('coding_2h', date, coding_time >= 120, coding_time)
            
            # 2. Learning 1h
            learning_time = 0
            for url, data in breakdown.get('top_urls', []):
                if any(kw in url.lower() for kw in ['docs', 'tutorial', 'course', 'learning']):
                    learning_time += data.get('minutes', 0)
            
            self.track_habit('learning_1h', date, learning_time >= 60, learning_time)
            
            # 3. Deep work 25m
            deep_work_periods = breakdown.get('deep_work_periods', [])
            has_deep_work = any(p['duration_minutes'] >= 25 for p in deep_work_periods)
            self.track_habit('deep_work_25m', date, has_deep_work, len(deep_work_periods))
            
            # 4. Goal alignment 50%
            try:
                alignment = goals.check_goal_alignment(date)
                alignment_pct = alignment.get('overall_alignment_percentage', 0)
                self.track_habit('goal_aligned_50pct', date, alignment_pct >= 50, alignment_pct)
            except:
                self.track_habit('goal_aligned_50pct', date, False, 0)
            
            # 5. Minimal distractions
            dist_data = distraction.track_distractions(start_time, end_time)
            dist_mins = dist_data.get('total_distraction_minutes', 0)
            self.track_habit('minimal_distractions', date, dist_mins < 30, dist_mins)
            
        except Exception as e:
            # Silently fail - some days might not have data
            pass
    
    def get_all_habits_summary(self) -> List[Dict]:
        """
        Get summary of all active habits.
        
        Returns:
            List of habit summaries with streaks and consistency
        """
        cursor = self.db.cursor()
        
        cursor.execute("SELECT name, description, target_value, unit FROM user_habits WHERE active = 1")
        
        habits = []
        for row in cursor.fetchall():
            name = row[0]
            
            habits.append({
                'name': name,
                'description': row[1],
                'target_value': row[2],
                'unit': row[3],
                'current_streak': self.get_current_streak(name),
                'longest_streak': self.get_longest_streak(name),
                'consistency_30d': round(self.get_consistency_score(name, 30), 1),
                'consistency_7d': round(self.get_consistency_score(name, 7), 1)
            })
        
        return habits
    
    def get_habit_calendar(self, habit_name: str, days: int = 30) -> List[Dict]:
        """
        Get calendar view of habit completions.
        
        Returns:
            List of {date, completed, value} for the last N days
        """
        cursor = self.db.cursor()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor.execute("""
            SELECT date, completed, value
            FROM habit_tracking
            WHERE habit_name = ? AND date >= ? AND date <= ?
            ORDER BY date DESC
        """, (
            habit_name,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        ))
        
        return [
            {
                'date': row[0],
                'completed': bool(row[1]),
                'value': row[2]
            }
            for row in cursor.fetchall()
        ]


def get_habit_analyzer(db_connection):
    """Get habit analyzer instance."""
    return HabitAnalyzer(db_connection)
