"""
Productivity Pattern Analyzer

Analyzes productivity patterns across time to identify:
- Peak performance hours
- Hourly productivity scores
- Weekly/monthly trends
- Productivity comparisons
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import statistics


class ProductivityPatternAnalyzer:
    """Analyzes productivity patterns from historical data."""
    
    def __init__(self, db_connection):
        """Initialize analyzer with database connection."""
        self.db = db_connection
        
        # Weights for productivity score calculation
        self.DEEP_WORK_WEIGHT = 0.4
        self.FOCUS_WEIGHT = 0.3
        self.EFFICIENCY_WEIGHT = 0.3
    
    def analyze_hourly_productivity(self, start_time: float, end_time: float) -> Dict[int, float]:
        """
        Analyze productivity for each hour of the day.
        
        Args:
            start_time: Start timestamp
            end_time: End timestamp
        
        Returns:
            Dictionary mapping hour (0-23) to productivity score (0-100)
        """
        from backend.services.time_tracker import get_time_tracker
        from backend.services.session_detector import get_session_detector
        
        tracker = get_time_tracker(self.db)
        detector = get_session_detector(self.db)
        
        hourly_scores = {}
        
        # Analyze each hour
        for hour in range(24):
            # Get data for this hour across all days in range
            hour_data = self._get_hour_data(start_time, end_time, hour)
            
            if not hour_data['total_time']:
                hourly_scores[hour] = 0
                continue
            
            # Calculate productivity score for this hour
            score = self._calculate_productivity_score(hour_data)
            hourly_scores[hour] = round(score, 1)
        
        return hourly_scores
    
    def _get_hour_data(self, start_time: float, end_time: float, hour: int) -> Dict:
        """Get aggregated data for a specific hour across the time range."""
        cursor = self.db.cursor()
        
        # Query actions within this hour across all days
        cursor.execute("""
            SELECT 
                timestamp,
                action_type,
                source
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
        """, (start_time, end_time))
        
        actions_in_hour = []
        for row in cursor.fetchall():
            action_time = datetime.fromtimestamp(row[0])
            if action_time.hour == hour:
                actions_in_hour.append({
                    'timestamp': row[0],
                    'type': row[1],
                    'source': row[2]
                })
        
        if not actions_in_hour:
            return {
                'total_time': 0,
                'deep_work_time': 0,
                'action_count': 0,
                'expected_actions': 60  # ~1 per minute for active hour
            }
        
        # Calculate metrics
        total_time = len(actions_in_hour) * 60  # Rough estimate: 1 action = 1 min engaged
        deep_work_time = self._estimate_deep_work(actions_in_hour)
        
        return {
            'total_time': total_time,
            'deep_work_time': deep_work_time,
            'action_count': len(actions_in_hour),
            'expected_actions': 60
        }
    
    def _estimate_deep_work(self, actions: List[Dict]) -> int:
        """Estimate deep work minutes from actions."""
        if len(actions) < 10:
            return 0
        
        # Group actions by 5-minute windows
        deep_work_minutes = 0
        current_window = []
        window_start = actions[0]['timestamp']
        
        for action in actions:
            if action['timestamp'] - window_start <= 300:  # 5 min window
                current_window.append(action)
            else:
                # Check if window qualifies as deep work (>=3 actions)
                if len(current_window) >= 3:
                    deep_work_minutes += 5
                current_window = [action]
                window_start = action['timestamp']
        
        return deep_work_minutes
    
    def _calculate_productivity_score(self, hour_data: Dict) -> float:
        """
        Calculate productivity score (0-100) for an hour.
        
        Formula:
        score = (deep_work_weight * deep_work_ratio +
                 efficiency_weight * action_efficiency) * 100
        """
        total_time = hour_data['total_time']
        if total_time == 0:
            return 0
        
        # Deep work component (0-1)
        deep_work_ratio = min(1.0, hour_data['deep_work_time'] / total_time)
        
        # Efficiency component (0-1)
        action_efficiency = min(1.0, hour_data['action_count'] / hour_data['expected_actions'])
        
        # Weighted score
        score = (
            self.DEEP_WORK_WEIGHT * deep_work_ratio +
            self.EFFICIENCY_WEIGHT * action_efficiency
        ) * 100
        
        # Add focus bonus if both metrics are high
        if deep_work_ratio > 0.5 and action_efficiency > 0.5:
            score = min(100, score * 1.2)
        
        return score
    
    def get_peak_hours(self, days: int = 30) -> List[Tuple[str, float]]:
        """
        Get top 3 most productive hours of the day.
        
        Args:
            days: Number of days to analyze (default: 30)
        
        Returns:
            List of (time_range, score) tuples
        """
        end_time = datetime.now().timestamp()
        start_time = (datetime.now() - timedelta(days=days)).timestamp()
        
        hourly_scores = self.analyze_hourly_productivity(start_time, end_time)
        
        # Sort by score and get top 3
        sorted_hours = sorted(hourly_scores.items(), key=lambda x: x[1], reverse=True)
        peak_hours = []
        
        for hour, score in sorted_hours[:3]:
            if score > 0:  # Only include hours with activity
                time_range = f"{hour:02d}:00-{(hour+1):02d}:00"
                peak_hours.append((time_range, score))
        
        return peak_hours
    
    def compare_weeks(self, week1_start: float, week2_start: float) -> Dict:
        """
        Compare two weeks of productivity.
        
        Args:
            week1_start: Start timestamp of first week
            week2_start: Start timestamp of second week
        
        Returns:
            Comparison dictionary with deltas
        """
        week1_end = week1_start + (7 * 24 * 3600)
        week2_end = week2_start + (7 * 24 * 3600)
        
        # Get metrics for both weeks
        week1_metrics = self._get_week_metrics(week1_start, week1_end)
        week2_metrics = self._get_week_metrics(week2_start, week2_end)
        
        # Calculate changes
        def calc_change(new, old):
            if old == 0:
                return 0
            return ((new - old) / old) * 100
        
        return {
            'week1': week1_metrics,
            'week2': week2_metrics,
            'changes': {
                'productivity_change': calc_change(
                    week2_metrics['avg_productivity'],
                    week1_metrics['avg_productivity']
                ),
                'focus_change': calc_change(
                    week2_metrics['avg_focus_score'],
                    week1_metrics['avg_focus_score']
                ),
                'time_change': calc_change(
                    week2_metrics['total_hours'],
                    week1_metrics['total_hours']
                )
            }
        }
    
    def _get_week_metrics(self, start_time: float, end_time: float) -> Dict:
        """Get aggregated metrics for a week."""
        from backend.services.time_tracker import get_time_tracker
        from backend.services.session_detector import get_session_detector
        
        tracker = get_time_tracker(self.db)
        sessions = get_session_detector(self.db).detect_sessions(start_time, end_time)
        
        # Calculate total time
        total_seconds = sum(s.get('duration_seconds', s['duration_minutes'] * 60) for s in sessions)
        total_hours = total_seconds / 3600
        
        # Get average productivity score
        hourly_scores = self.analyze_hourly_productivity(start_time, end_time)
        active_hours = [score for score in hourly_scores.values() if score > 0]
        avg_productivity = statistics.mean(active_hours) if active_hours else 0
        
        # Get focus scores from daily breakdowns
        focus_scores = []
        current = datetime.fromtimestamp(start_time)
        end_dt = datetime.fromtimestamp(end_time)
        
        while current <= end_dt:
            date_str = current.strftime('%Y-%m-%d')
            try:
                breakdown = tracker.get_daily_breakdown(date_str)
                if breakdown.get('productivity', {}).get('focus_score', 0) > 0:
                    focus_scores.append(breakdown['productivity']['focus_score'])
            except:
                pass
            current += timedelta(days=1)
        
        avg_focus = statistics.mean(focus_scores) if focus_scores else 0
        
        return {
            'total_hours': round(total_hours, 1),
            'avg_productivity': round(avg_productivity, 1),
            'avg_focus_score': round(avg_focus, 1),
            'session_count': len(sessions)
        }
    
    def generate_heatmap_data(self, days: int = 7) -> List[List[float]]:
        """
        Generate heatmap data (24x7 matrix) for visualization.
        
        Args:
            days: Number of days (default: 7 for week view)
        
        Returns:
            2D list: [day][hour] = productivity_score
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        heatmap = []
        
        # For each day
        current_day = start_time
        while current_day <= end_time:
            day_scores = []
            
            # For each hour in the day
            for hour in range(24):
                hour_start = current_day.replace(hour=hour, minute=0, second=0)
                hour_end = hour_start + timedelta(hours=1)
                
                hour_data = self._get_hour_data(
                    hour_start.timestamp(),
                    hour_end.timestamp(),
                    hour
                )
                
                score = self._calculate_productivity_score(hour_data)
                day_scores.append(round(score, 1))
            
            heatmap.append(day_scores)
            current_day += timedelta(days=1)
        
        return heatmap


def get_productivity_pattern_analyzer(db_connection):
    """Get productivity pattern analyzer instance."""
    return ProductivityPatternAnalyzer(db_connection)
