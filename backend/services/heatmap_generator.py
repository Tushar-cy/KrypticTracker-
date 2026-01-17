"""
Heatmap Generator

Generates visual ASCII/Unicode heatmaps for productivity patterns in the TUI.
"""

from datetime import datetime, timedelta
from typing import List, Dict
from backend.services.productivity_patterns import get_productivity_pattern_analyzer


class HeatmapGenerator:
    """Generates productivity heatmaps for TUI visualization."""
    
    # Unicode block characters for heatmap intensity
    INTENSITY_CHARS = {
        'none': '░░',      # 0-10
        'very_low': '▒▒',  # 11-25
        'low': '▓▓',       # 26-50
        'medium': '██',   # 51-75
        'high': '██',     # 76-100  (same as medium but different color)
    }
    
    def __init__(self, db_connection):
        """Initialize heatmap generator."""
        self.db = db_connection
        self.analyzer = get_productivity_pattern_analyzer(db_connection)
    
    def generate_weekly_heatmap(self, end_date: datetime = None) -> str:
        """
        Generate a 24x7 productivity heatmap for the last week.
        
        Returns:
            Formatted ASCII heatmap string
        """
        if end_date is None:
            end_date = datetime.now()
        
        start_date = end_date - timedelta(days=6)  # 7 days total
        
        # Get heatmap data
        heatmap_data = self.analyzer.generate_heatmap_data(days=7)
        
        # Build the heatmap string
        lines = []
        
        # Title
        lines.append(f"Productivity Heatmap ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})")
        lines.append("")
        
        # Hour header
        hour_header = "      "
        for hour in range(0, 24, 2):  # Show every 2 hours
            hour_header += f"{hour:02d} "
        lines.append(hour_header)
        
        # Day rows
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        current = start_date
        
        for day_idx, day_scores in enumerate(heatmap_data[:7]):
            day_name = current.strftime("%a")
            row = f"{day_name}   "
            
            for hour_idx, score in enumerate(day_scores):
                # Get intensity character based on score
                if hour_idx % 2 == 0:  # Show every 2 hours
                    char = self._get_intensity_char(score)
                    row += f"{char} "
            
            lines.append(row)
            current += timedelta(days=1)
        
        # Legend
        lines.append("")
        lines.append("Legend: ░░ None (0-10)  ▒▒ Low (11-25)  ▓▓ Med (26-50)  ██ High (51-100)")
        
        return "\n".join(lines)
    
    def generate_daily_heatmap(self, date: datetime = None) -> str:
        """
        Generate hourly productivity bars for a single day.
        
        Returns:
            Formatted bar chart string
        """
        if date is None:
            date = datetime.now()
        
        # Get hourly scores for the day
        start_time = date.replace(hour=0, minute=0, second=0).timestamp()
        end_time = date.replace(hour=23, minute=59, second=59).timestamp()
        
        hourly_scores = self.analyzer.analyze_hourly_productivity(start_time, end_time)
        
        lines = []
        lines.append(f"Hourly Productivity - {date.strftime('%B %d, %Y')}")
        lines.append("")
        
        # Find max score for scaling
        max_score = max(hourly_scores.values()) if hourly_scores else 100
        if max_score == 0:
            max_score = 100
        
        # Generate bars
        for hour in range(24):
            score = hourly_scores.get(hour, 0)
            bar_length = int((score / max_score) * 30)  # Scale to 30 chars
            
            # Color based on score
            if score >= 75:
                bar = "█" * bar_length
                color_indicator = "🔥"
            elif score >= 50:
                bar = "▓" * bar_length
                color_indicator = "💪"
            elif score >= 25:
                bar = "▒" * bar_length
                color_indicator = "📊"
            else:
                bar = "░" * bar_length
                color_indicator = "💤" if score > 0 else "  "
            
            time_label = f"{hour:02d}:00"
            score_label = f"{score:5.1f}" if score > 0 else "  ---"
            
            lines.append(f"{time_label}  {color_indicator} {bar:<30} {score_label}")
        
        return "\n".join(lines)
    
    def generate_comparison_heatmap(self, weeks_back: int = 4) -> str:
        """
        Generate a comparison heatmap showing multiple weeks.
        
        Returns:
            Formatted multi-week heatmap
        """
        lines = []
        lines.append(f"Weekly Productivity Comparison (Last {weeks_back} Weeks)")
        lines.append("")
        
        end_date = datetime.now()
        
        for week_num in range(weeks_back):
            week_end = end_date - timedelta(weeks=week_num)
            week_start = week_end - timedelta(days=6)
            
            # Get week's data
            heatmap_data = self.analyzer.generate_heatmap_data(days=7)
            
            # Calculate average productivity for the week
            all_scores = [score for day in heatmap_data for score in day if score > 0]
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            
            # Generate week summary line
            week_label = f"Week {weeks_back - week_num}"
            date_range = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
            
            # Visual bar
            bar_length = int((avg_score / 100) * 20)
            bar = "█" * bar_length + "░" * (20 - bar_length)
            
            # Trend indicator
            if week_num < weeks_back - 1:
                # Compare to previous week
                prev_week_end = end_date - timedelta(weeks=week_num + 1)
                prev_week_start = prev_week_end - timedelta(days=6)
                prev_data = self.analyzer.generate_heatmap_data(days=7)
                prev_scores = [score for day in prev_data for score in day if score > 0]
                prev_avg = sum(prev_scores) / len(prev_scores) if prev_scores else 0
                
                if avg_score > prev_avg + 5:
                    trend = "↑"
                elif avg_score < prev_avg - 5:
                    trend = "↓"
                else:
                    trend = "→"
            else:
                trend = " "
            
            lines.append(f"{week_label:8} {date_range:20} {bar} {avg_score:5.1f} {trend}")
        
        return "\n".join(lines)
    
    def _get_intensity_char(self, score: float) -> str:
        """Get Unicode character for score intensity."""
        if score <= 10:
            return self.INTENSITY_CHARS['none']
        elif score <= 25:
            return self.INTENSITY_CHARS['very_low']
        elif score <= 50:
            return self.INTENSITY_CHARS['low']
        elif score <= 75:
            return self.INTENSITY_CHARS['medium']
        else:
            return self.INTENSITY_CHARS['high']
    
    def generate_project_heatmap(self, project_name: str, days: int = 30) -> str:
        """
        Generate heatmap for a specific project.
        
        Returns:
            Project-specific heatmap showing activity intensity
        """
        cursor = self.db.cursor()
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # Get project activity by day and hour
        lines = []
        lines.append(f"Project Activity Heatmap: {project_name}")
        lines.append(f"Period: {start_time.strftime('%b %d')} - {end_time.strftime('%b %d')}")
        lines.append("")
        
        # Query actions for this project
        cursor.execute("""
            SELECT timestamp FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            AND (context_json LIKE ? OR context_json LIKE ?)
        """, (
            start_time.timestamp(),
            end_time.timestamp(),
            f'%"project": "{project_name}"%',
            f'%"working_directory"%{project_name}%'
        ))
        
        # Build hourly activity map
        activity_map = {}
        for row in cursor.fetchall():
            dt = datetime.fromtimestamp(row[0])
            day_key = dt.strftime('%Y-%m-%d')
            hour = dt.hour
            
            if day_key not in activity_map:
                activity_map[day_key] = [0] * 24
            activity_map[day_key][hour] += 1
        
        # Find max activity for scaling
        max_activity = max(
            max(hours) for hours in activity_map.values()
        ) if activity_map else 1
        
        # Generate heatmap
        current = start_time
        while current <= end_time:
            day_key = current.strftime('%Y-%m-%d')
            day_label = current.strftime('%b %d')
            
            if day_key in activity_map:
                row = f"{day_label}  "
                for hour in range(0, 24, 2):
                    activity = activity_map[day_key][hour]
                    intensity = (activity / max_activity) * 100 if max_activity > 0 else 0
                    char = self._get_intensity_char(intensity)
                    row += f"{char} "
                lines.append(row)
            
            current += timedelta(days=1)
        
        return "\n".join(lines)


def get_heatmap_generator(db_connection):
    """Get heatmap generator instance."""
    return HeatmapGenerator(db_connection)
