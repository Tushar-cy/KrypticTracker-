"""
Pattern Detection Service

Identifies productivity patterns, blockers, workflows, and optimal work environments.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict, Counter
import json
import statistics


class PatternDetector:
    """Detects productivity patterns from historical data."""
    
    def __init__(self, db_connection):
        """Initialize pattern detector."""
        self.db = db_connection
    
    def detect_work_environments(self, days: int = 30) -> List[Dict]:
        """
        Find app combinations that correlate with high productivity.
        
        Returns:
            List of {apps, avg_productivity, frequency, recommendation}
        """
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        cursor = self.db.cursor()
        
        # Get sessions from the last N days
        end_time = datetime.now().timestamp()
        start_time = (datetime.now() - timedelta(days=days)).timestamp()
        
        cursor.execute("""
            SELECT start_time, end_time, metadata
            FROM work_sessions
            WHERE start_time >= ? AND start_time <= ?
        """, (start_time, end_time))
        
        # Analyze app combinations
        environment_scores = defaultdict(lambda: {'scores': [], 'count': 0})
        
        for row in cursor.fetchall():
            session_start = row[0]
            session_end = row[1]
            metadata = json.loads(row[2]) if row[2] else {}
            
            # Get apps used in this session
            apps = metadata.get('apps', [])
            if len(apps) < 2:
                continue
            
            # Create environment key (sorted apps)
            env_key = tuple(sorted(apps[:5]))  # Top 5 apps
            
            # Calculate productivity score for this time period
            hourly_scores = analyzer.analyze_hourly_productivity(session_start, session_end)
            if hourly_scores:
                avg_score = statistics.mean([s for s in hourly_scores.values() if s > 0])
                environment_scores[env_key]['scores'].append(avg_score)
                environment_scores[env_key]['count'] += 1
        
        # Compile results
        results = []
        for apps, data in environment_scores.items():
            if data['count'] < 3:  # Need at least 3 sessions
                continue
            
            avg_productivity = statistics.mean(data['scores'])
            
            results.append({
                'apps': list(apps),
                'avg_productivity': round(avg_productivity, 1),
                'frequency': data['count'],
                'recommendation': self._generate_environment_recommendation(avg_productivity)
            })
        
        # Sort by productivity
        results.sort(key=lambda x: x['avg_productivity'], reverse=True)
        return results[:10]
    
    def _generate_environment_recommendation(self, score: float) -> str:
        """Generate recommendation based on productivity score."""
        if score >= 75:
            return "Highly productive environment! Use for important tasks."
        elif score >= 50:
            return "Good productivity. Suitable for most work."
        elif score >= 25:
            return "Moderate productivity. Consider optimizing."
        else:
            return "Low productivity. Review if this setup serves you."
    
    def identify_blockers(self, days: int = 30) -> List[Dict]:
        """
        Detect patterns that reduce productivity.
        
        Returns:
            List of {pattern, impact, suggestion, frequency}
        """
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        cursor = self.db.cursor()
        
        blockers = []
        
        # 1. Late start times
        late_starts = self._detect_late_starts(days)
        if late_starts['count'] > 0:
            blockers.append({
                'pattern': f"Starting work after {late_starts['threshold']}",
                'impact': f"-{late_starts['productivity_drop']:.0f}% productivity",
                'suggestion': f"Try starting by {late_starts['optimal_time']} for better results",
                'frequency': late_starts['count']
            })
        
        # 2. Long distraction periods
        long_distractions = self._detect_long_distractions(days)
        if long_distractions['count'] > 0:
            blockers.append({
                'pattern': f"Distraction sessions > {long_distractions['threshold']}min",
                'impact': f"{long_distractions['time_lost']}h total lost",
                'suggestion': "Set 15-min timers for break activities",
                'frequency': long_distractions['count']
            })
        
        # 3. Context switch storms
        switch_storms = self._detect_switch_storms(days)
        if switch_storms['count'] > 0:
            blockers.append({
                'pattern': f">{switch_storms['threshold']} app switches per hour",
                'impact': f"{switch_storms['cost_hours']:.1f}h recovery time",
                'suggestion': "Use focus mode or app blockers during deep work",
                'frequency': switch_storms['count']
            })
        
        return blockers
    
    def _detect_late_starts(self, days: int) -> Dict:
        """Detect if starting late impacts productivity."""
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        cursor = self.db.cursor()
        
        # Get first action time for each day
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        early_scores = []
        late_scores = []
        late_count = 0
        
        current = start_date
        while current <= end_date:
            date_str = current.strftime('%Y-%m-%d')
            day_start = current.replace(hour=0, minute=0, second=0).timestamp()
            day_end = current.replace(hour=23, minute=59, second=59).timestamp()
            
            # Get first action
            cursor.execute("""
                SELECT timestamp FROM actions
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC LIMIT 1
            """, (day_start, day_end))
            
            row = cursor.fetchone()
            if row:
                first_action_time = datetime.fromtimestamp(row[0])
                hour = first_action_time.hour
                
                # Get average productivity for the day
                hourly_scores = analyzer.analyze_hourly_productivity(day_start, day_end)
                day_avg = statistics.mean([s for s in hourly_scores.values() if s > 0]) if hourly_scores else 0
                
                if hour <= 9:
                    early_scores.append(day_avg)
                else:
                    late_scores.append(day_avg)
                    late_count += 1
            
            current += timedelta(days=1)
        
        if not early_scores or not late_scores:
            return {'count': 0}
        
        early_avg = statistics.mean(early_scores)
        late_avg = statistics.mean(late_scores)
        drop = early_avg - late_avg
        
        if drop > 10:  # Significant drop
            return {
                'count': late_count,
                'threshold': '10:00 AM',
                'productivity_drop': drop,
                'optimal_time': '9:00 AM'
            }
        
        return {'count': 0}
    
    def _detect_long_distractions(self, days: int) -> Dict:
        """Detect long distraction periods."""
        from backend.services.distraction_tracker import get_distraction_tracker
        
        tracker = get_distraction_tracker(self.db)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        long_dist_count = 0
        total_time_lost = 0
        
        current = start_date
        while current <= end_date:
            day_start = current.replace(hour=0, minute=0, second=0).timestamp()
            day_end = current.replace(hour=23, minute=59, second=59).timestamp()
            
            dist_data = tracker.track_distractions(day_start, day_end)
            
            # Check events > 20 min
            for event in dist_data.get('distraction_events', []):
                if event['duration_minutes'] > 20:
                    long_dist_count += 1
                    total_time_lost += event['duration_minutes']
            
            current += timedelta(days=1)
        
        if long_dist_count > 0:
            return {
                'count': long_dist_count,
                'threshold': 20,
                'time_lost': round(total_time_lost / 60, 1)
            }
        
        return {'count': 0}
    
    def _detect_switch_storms(self, days: int) -> Dict:
        """Detect periods of excessive context switching."""
        from backend.services.distraction_tracker import get_distraction_tracker
        
        tracker = get_distraction_tracker(self.db)
        
        storm_count = 0
        total_cost = 0
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        current = start_date
        while current <= end_date:
            day_start = current.replace(hour=0, minute=0, second=0).timestamp()
            day_end = current.replace(hour=23, minute=59, second=59).timestamp()
            
            dist_data = tracker.track_distractions(day_start, day_end)
            switches = dist_data.get('context_switches', 0)
            
            # Assuming 8-hour workday
            switches_per_hour = switches / 8 if switches > 0 else 0
            
            if switches_per_hour > 10:  # More than 10 per hour
                storm_count += 1
                total_cost += (switches * 23) / 60  # 23 min cost per switch, convert to hours
            
            current += timedelta(days=1)
        
        if storm_count > 0:
            return {
                'count': storm_count,
                'threshold': 10,
                'cost_hours': total_cost
            }
        
        return {'count': 0}
    
    def extract_workflows(self, min_frequency: int = 3) -> List[Dict]:
        """
        Identify common task sequences (workflows).
        
        Returns:
            List of {name, steps, frequency, success_rate}
        """
        cursor = self.db.cursor()
        
        # Get action sequences
        cursor.execute("""
            SELECT action_type, source, context_json, timestamp
            FROM actions
            ORDER BY timestamp ASC
        """)
        
        # Build sequences (within 5-minute windows)
        sequences = []
        current_sequence = []
        last_timestamp = None
        
        for row in cursor.fetchall():
            action_type = row[0]
            source = row[1]
            timestamp = row[3]
            
            action_sig = f"{source}:{action_type}"
            
            if last_timestamp is None or (timestamp - last_timestamp) < 300:  # 5 min
                current_sequence.append(action_sig)
            else:
                if len(current_sequence) >= 3:
                    sequences.append(tuple(current_sequence))
                current_sequence = [action_sig]
            
            last_timestamp = timestamp
        
        # Count frequencies
        sequence_counts = Counter(sequences)
        
        # Build workflow results
        workflows = []
        for sequence, count in sequence_counts.most_common(20):
            if count >= min_frequency:
                workflows.append({
                    'name': self._generate_workflow_name(sequence),
                    'steps': list(sequence),
                    'frequency': count,
                    'success_rate': 100  # TODO: Calculate based on completion
                })
        
        return workflows
    
    def _generate_workflow_name(self, sequence: Tuple[str, ...]) -> str:
        """Generate a readable name for a workflow."""
        # Extract key actions
        actions = [s.split(':')[1] if ':' in s else s for s in sequence]
        
        if 'git' in str(sequence).lower():
            return "Git Workflow"
        elif 'file' in str(sequence).lower():
            return "File Operations"
        elif 'browser' in str(sequence).lower():
            return "Research Workflow"
        else:
            return f"{actions[0]} → ... → {actions[-1]}"
    
    def find_optimal_task_times(self) -> Dict[str, str]:
        """
        Find best times for different task types.
        
        Returns:
            dict mapping task type to optimal time range
        """
        # Simplified version - could be enhanced with ML
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        analyzer = get_productivity_pattern_analyzer(self.db)
        peak_hours = analyzer.get_peak_hours(days=30)
        
        if not peak_hours:
            return {
                'coding': "09:00-11:00",
                'research': "14:00-16:00",
                'meetings': "13:00-15:00"
            }
        
        # Use top peak hour for coding
        peak = peak_hours[0][0]
        
        return {
            'coding': peak,
            'research': f"{int(peak.split('-')[0].split(':')[0]) + 2:02d}:00-{int(peak.split('-')[0].split(':')[0]) + 4:02d}:00",
            'meetings': "13:00-15:00",  # Typically lower energy post-lunch
            'learning': peak
        }


def get_pattern_detector(db_connection):
    """Get pattern detector instance."""
    return PatternDetector(db_connection)
