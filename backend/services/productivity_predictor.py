"""
Productivity Predictor Service

Predicts productivity, suggests optimal work times, and recommends breaks.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import statistics


class ProductivityPredictor:
    """Predicts productivity and suggests optimal schedules."""
    
    def __init__(self, db_connection):
        """Initialize predictor."""
        self.db = db_connection
    
    def predict_today(self, current_hour: Optional[int] = None) -> Dict:
        """
        Predict today's productivity based on current progress.
        
        Args:
            current_hour: Current hour (uses now() if None)
        
        Returns:
            {predicted_score, confidence, reasoning}
        """
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        if current_hour is None:
            current_hour = datetime.now().hour
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        
        # Get today's data so far
        today = datetime.now()
        start_of_day = today.replace(hour=0, minute=0, second=0).timestamp()
        current_time = today.timestamp()
        
        hourly_scores = analyzer.analyze_hourly_productivity(start_of_day, current_time)
        
        # Get historical data for this day of week
        day_of_week = today.weekday()
        historical_scores = self._get_historical_day_scores(day_of_week, weeks=4)
        
        if not hourly_scores:
            # No data yet today - use historical average
            if historical_scores:
                predicted = statistics.mean(historical_scores)
                confidence = 0.6
                reasoning = f"Based on your typical {today.strftime('%A')} performance"
            else:
                predicted = 50
                confidence = 0.3
                reasoning = "Insufficient historical data"
        else:
            # We have some data - extrapolate
            current_avg = statistics.mean([s for s in hourly_scores.values() if s > 0])
            
            if historical_scores:
                historical_avg = statistics.mean(historical_scores)
                # Weighted average (60% current, 40% historical)
                predicted = (current_avg * 0.6) + (historical_avg * 0.4)
                confidence = min(0.9, 0.5 + (current_hour / 24))
                reasoning = f"Based on {current_hour}h of data + historical patterns"
            else:
                predicted = current_avg
                confidence = min(0.8, 0.4 + (current_hour / 24))
                reasoning = f"Extrapolating from {current_hour}h of data"
        
        return {
            'predicted_score': round(predicted, 1),
            'confidence': round(confidence, 2),
            'reasoning': reasoning,
            'current_hour': current_hour
        }
    
    def _get_historical_day_scores(self, day_of_week: int, weeks: int = 4) -> List[float]:
        """Get historical productivity scores for a specific day of week."""
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        scores = []
        
        # Look back at the last N weeks
        today = datetime.now().date()
        for week_back in range(1, weeks + 1):
            target_date = today - timedelta(weeks=week_back)
            # Adjust to the target day of week
            days_diff = target_date.weekday() - day_of_week
            target_date -= timedelta(days=days_diff)
            
            day_start = datetime.combine(target_date, datetime.min.time()).timestamp()
            day_end = datetime.combine(target_date, datetime.max.time()).timestamp()
            
            hourly = analyzer.analyze_hourly_productivity(day_start, day_end)
            if hourly:
                day_avg = statistics.mean([s for s in hourly.values() if s > 0])
                scores.append(day_avg)
        
        return scores
    
    def suggest_break_time(self) -> Dict:
        """
        Recommend when to take next break.
        
        Returns:
            {suggested_time, reason, duration_minutes, urgency}
        """
        cursor = self.db.cursor()
        
        # Find the last break-like period (low activity)
        now = datetime.now()
        last_4_hours = (now - timedelta(hours=4)).timestamp()
        
        cursor.execute("""
            SELECT timestamp, action_type, source
            FROM actions
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, (last_4_hours,))
        
        actions = cursor.fetchall()
        if not actions:
            return {
                'suggested_time': 'Now',
                'reason': 'No recent activity detected',
                'duration_minutes': 10,
                'urgency': 'low'
            }
        
        # Find gaps (potential breaks)
        last_break = None
        last_timestamp = None
        continuous_work = 0
        
        for action in actions:
            timestamp = action[0]
            
            if last_timestamp:
                gap = (timestamp - last_timestamp) / 60  # minutes
                
                if gap > 15:  # Likely a break
                    last_break = timestamp
                    continuous_work = 0
                else:
                    continuous_work += gap
            
            last_timestamp = timestamp
        
        # Calculate time since last break
        if last_break:
            minutes_since_break = (now.timestamp() - last_break) / 60
        else:
            minutes_since_break = continuous_work
        
        # Determine recommendation
        if minutes_since_break >= 120:  # 2 hours
            return {
                'suggested_time': 'Immediately',
                'reason': f'{int(minutes_since_break)}min of continuous work',
                'duration_minutes': 15,
                'urgency': 'high'
            }
        elif minutes_since_break >= 90:  # 1.5 hours
            return {
                'suggested_time': 'Within 15 minutes',
                'reason': 'Approaching focus fatigue',
                'duration_minutes': 10,
                'urgency': 'medium'
            }
        elif minutes_since_break >= 60:  # 1 hour
            return {
                'suggested_time': 'Within 30 minutes',
                'reason': 'Maintain sustainable pace',
                'duration_minutes': 5,
                'urgency': 'low'
            }
        else:
            next_break = 60 - int(minutes_since_break)
            return {
                'suggested_time': f'In {next_break} minutes',
                'reason': 'On track with break schedule',
                'duration_minutes': 5,
                'urgency': 'none'
            }
    
    def predict_energy_level(self, hour: int) -> Dict:
        """
        Predict energy level for a specific hour.
        
        Returns:
            {energy: "high"|"medium"|"low", confidence, productivity_score}
        """
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        
        # Get historical data for this hour across multiple days
        cursor = self.db.cursor()
        scores = []
        
        for days_back in range(1, 15):  # Last 2 weeks
            date = datetime.now() - timedelta(days=days_back)
            hour_start = date.replace(hour=hour, minute=0, second=0).timestamp()
            hour_end = date.replace(hour=hour, minute=59, second=59).timestamp()
            
            hourly = analyzer.analyze_hourly_productivity(hour_start, hour_end)
            if hour in hourly and hourly[hour] > 0:
                scores.append(hourly[hour])
        
        if not scores:
            return {
                'energy': 'medium',
                'confidence': 0.3,
                'productivity_score': 50
            }
        
        avg_score = statistics.mean(scores)
        confidence = min(0.9, len(scores) / 14)  # More data = higher confidence
        
        if avg_score >= 70:
            energy = 'high'
        elif avg_score >= 40:
            energy = 'medium'
        else:
            energy = 'low'
        
        return {
            'energy': energy,
            'confidence': round(confidence, 2),
            'productivity_score': round(avg_score, 1)
        }
    
    def recommend_task_scheduling(self, tasks: List[Dict]) -> List[Dict]:
        """
        Suggest optimal schedule for tasks.
        
        Args:
            tasks: List of {name, estimated_minutes, priority}
        
        Returns:
            List of {task, start_time, reason}
        """
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        
        # Get peak hours
        peak_hours = analyzer.get_peak_hours(days=7)
        if not peak_hours:
            # Default schedule
            return [
                {
                    'task': task['name'],
                    'start_time': '09:00',
                    'reason': 'Default morning schedule'
                }
                for task in tasks
            ]
        
        # Sort tasks by priority
        sorted_tasks = sorted(tasks, key=lambda x: x.get('priority', 0), reverse=True)
        
        schedule = []
        current_hour = datetime.now().hour
        
        # Assign high-priority tasks to peak hours
        for i, task in enumerate(sorted_tasks):
            if i < len(peak_hours):
                peak_time = peak_hours[i][0].split('-')[0]  # Get start time
                reason = f"Peak productivity hour (score: {peak_hours[i][1]:.0f})"
            else:
                # Use next available hour
                peak_time = f"{(current_hour + i) % 24:02d}:00"
                reason = "Next available time slot"
            
            schedule.append({
                'task': task['name'],
                'start_time': peak_time,
                'reason': reason,
                'estimated_duration': task.get('estimated_minutes', 30)
            })
        
        return schedule


def get_productivity_predictor(db_connection):
    """Get productivity predictor instance."""
    return ProductivityPredictor(db_connection)
