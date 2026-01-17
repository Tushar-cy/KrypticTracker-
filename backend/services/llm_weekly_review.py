"""
LLM Weekly Review Service

Generates comprehensive weekly productivity reviews using LLM analysis.
"""

from datetime import datetime, timedelta
from typing import Dict, List
import json


class LLMWeeklyReview:
    """Generates LLM-powered weekly productivity reviews."""
    
    WEEKLY_REVIEW_PROMPT = """You are a productivity coach analyzing a week of work data.

**WEEK DATA ({week_start} to {week_end})**

📊 **STATISTICS:**
- Total Time: {total_hours}h ({change_vs_last_week}% vs last week)
- Focus Score: {avg_focus}/100 ({focus_trend})
- Top Project: {top_project} ({project_hours}h, {project_pct}%)
- Goal Alignment: {goal_alignment_pct}%
- Distractions: {distraction_time}
- Context Switches: {context_switches}
- Peak Hours: {peak_hours}
- Top 3 Apps: {top_apps}

🎯 **HABITS:**
{habits_status}

📈 **SESSIONS:**
- Total Sessions: {total_sessions}
- Coding: {coding_sessions} sessions
- Research: {research_sessions} sessions  
- Average Session Length: {avg_session_length}min

⚡ **PRODUCTIVITY PATTERNS:**
- Most Productive Day: {best_day} ({best_day_score}/100)
- Least Productive Day: {worst_day} ({worst_day_score}/100)
- Best Time Slot: {best_time}
- Blockers Detected: {blockers_count}

Generate a concise, motivating weekly review with:

1. **🎯 Top 3 Accomplishments** (what went well this week)
2. **⚠️ 2 Areas for Improvement** (specific, actionable)  
3. **💡 1 Key Productivity Insight** (pattern-based tip)
4. **📅 Next Week Focus** (one concrete goal)

Keep it under 200 words total. Be honest but encouraging. Use emojis sparingly. Focus on actionable insights.
"""
    
    def __init__(self, db_connection):
        """Initialize weekly review generator."""
        self.db = db_connection
    
    def generate_weekly_review(self, week_offset: int = 0) -> Dict:
        """
        Generate a weekly productivity review.
        
        Args:
            week_offset: Weeks back (0 = this week, 1 = last week)
        
        Returns:
            {review_text, raw_data, week_start, week_end}
        """
        from backend.services.llm_service import get_llm_service
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        from backend.services.distraction_tracker import get_distraction_tracker
        from backend.services.time_tracker import get_time_tracker
        from backend.services.session_detector import get_session_detector
        from backend.services.habit_analyzer import get_habit_analyzer
        from backend.services.goal_service import get_goal_service
        from backend.services.pattern_detector import get_pattern_detector
        
        # Calculate week boundaries
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
        week_end = week_start + timedelta(days=6)
        
        # Services
        llm = get_llm_service(self.db)
        analyzer = get_productivity_pattern_analyzer(self.db)
        distraction = get_distraction_tracker(self.db)
        tracker = get_time_tracker(self.db)
        sessions = get_session_detector(self.db)
        habits = get_habit_analyzer(self.db)
        goals = get_goal_service(self.db)
        patterns = get_pattern_detector(self.db)
        
        # Collect all data
        week_data = self._collect_week_data(
            week_start, week_end, analyzer, distraction, tracker, 
            sessions, habits, goals, patterns
        )
        
        # Generate review with LLM
        prompt = self._format_prompt(week_data)
        
        try:
            response = llm.chat(prompt, max_tokens=500)
            review_text = response.get('response', 'Unable to generate review')
        except:
            review_text = self._generate_fallback_review(week_data)
        
        return {
            'review_text': review_text,
            'raw_data': week_data,
            'week_start': week_start.strftime('%Y-%m-%d'),
            'week_end': week_end.strftime('%Y-%m-%d'),
            'generated_at': datetime.now().isoformat()
        }
    
    def _collect_week_data(self, week_start, week_end, analyzer, distraction, 
                          tracker, sessions, habits, goals, patterns) -> Dict:
        """Collect all relevant data for the week."""
        start_ts = datetime.combine(week_start, datetime.min.time()).timestamp()
        end_ts = datetime.combine(week_end, datetime.max.time()).timestamp()
        
        # Previous week for comparison
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = prev_week_start + timedelta(days=6)
        prev_start_ts = datetime.combine(prev_week_start, datetime.min.time()).timestamp()
        prev_end_ts = datetime.combine(prev_week_end, datetime.max.time()).timestamp()
        
        # Productivity data
        try:
            weekly_comp = analyzer.get_weekly_comparison(
                week_start.strftime('%Y-%m-%d'),
                week_end.strftime('%Y-%m-%d')
            )
            total_hours = weekly_comp['this_week']['total_hours']
            avg_focus = weekly_comp['this_week']['avg_productivity']
            change_vs_last = weekly_comp.get('productivity_change', 0)
        except:
            total_hours = 0
            avg_focus = 0
            change_vs_last = 0
        
        # Distraction data
        try:
            dist_data = distraction.track_distractions(start_ts, end_ts)
            distraction_time = f"{dist_data['total_distraction_minutes']:.0f}min"
            context_switches = dist_data['context_switches']
        except:
            distraction_time = "0min"
            context_switches = 0
        
        # Peak hours
        try:
            peak_hours = analyzer.get_peak_hours(days=7)
            peak_str = peak_hours[0][0] if peak_hours else "N/A"
        except:
            peak_str = "N/A"
        
        # Habits
        try:
            habit_summary = habits.get_all_habits_summary()
            habits_status = "\n".join([
                f"- {h['description']}: {h['current_streak']} day streak ({h['consistency_7d']:.0f}% this week)"
                for h in habit_summary[:3]
            ])
        except:
            habits_status = "- No habit data"
        
        # Sessions
        try:
            all_sessions = sessions.get_session_summary_by_day(
                week_start.strftime('%Y-%m-%d'),
                week_end.strftime('%Y-%m-%d')
            )
            total_sessions = len(all_sessions)
            coding_sessions = sum(1 for s in all_sessions if s.get('session_type') == 'coding')
            research_sessions = sum(1 for s in all_sessions if s.get('session_type') == 'research')
            avg_session_length = sum(s.get('duration_minutes', 0) for s in all_sessions) / max(total_sessions, 1)
        except:
            total_sessions = coding_sessions = research_sessions = 0
            avg_session_length = 0
        
        # Top project
        try:
            # Get project breakdown for the week
            projects = {}
            for day_offset in range(7):
                day = week_start + timedelta(days=day_offset)
                day_str = day.strftime('%Y-%m-%d')
                breakdown = tracker.get_daily_breakdown(day_str)
                for proj, data in breakdown.get('by_project', {}).items():
                    projects[proj] = projects.get(proj, 0) + data.get('minutes', 0)
            
            if projects:
                top_project = max(projects.items(), key=lambda x: x[1])
                project_name = top_project[0]
                project_mins = top_project[1]
                project_hours = project_mins / 60
                project_pct = (project_mins / (total_hours * 60)) * 100 if total_hours > 0 else 0
            else:
                project_name = "None"
                project_hours = 0
                project_pct = 0
        except:
            project_name = "None"
            project_hours = 0
            project_pct = 0
        
        # Goal alignment
        try:
            # Average alignment across the week
            alignments = []
            for day_offset in range(7):
                day = week_start + timedelta(days=day_offset)
                day_str = day.strftime('%Y-%m-%d')
                align = goals.check_goal_alignment(day_str)
                alignments.append(align.get('overall_alignment_percentage', 0))
            goal_alignment_pct = sum(alignments) / len(alignments) if alignments else 0
        except:
            goal_alignment_pct = 0
        
        # Patterns
        try:
            blockers = patterns.identify_blockers(days=7)
            blockers_count = len(blockers)
        except:
            blockers_count = 0
        
        # Daily scores for best/worst day
        try:
            daily_scores = {}
            for day_offset in range(7):
                day = week_start + timedelta(days=day_offset)
                day_start = datetime.combine(day, datetime.min.time()).timestamp()
                day_end = datetime.combine(day, datetime.max.time()).timestamp()
                hourly = analyzer.analyze_hourly_productivity(day_start, day_end)
                if hourly:
                    import statistics
                    daily_scores[day.strftime('%A')] = statistics.mean([s for s in hourly.values() if s > 0])
            
            if daily_scores:
                best_day = max(daily_scores.items(), key=lambda x: x[1])
                worst_day = min(daily_scores.items(), key=lambda x: x[1])
            else:
                best_day = ("N/A", 0)
                worst_day = ("N/A", 0)
        except:
            best_day = ("N/A", 0)
            worst_day = ("N/A", 0)
        
        return {
            'week_start': week_start.strftime('%b %d'),
            'week_end': week_end.strftime('%b %d'),
            'total_hours': f"{total_hours:.1f}",
            'change_vs_last_week': f"{change_vs_last:+.0f}",
            'avg_focus': f"{avg_focus:.0f}",
            'focus_trend': "↑" if change_vs_last > 0 else "↓" if change_vs_last < 0 else "→",
            'top_project': project_name,
            'project_hours': f"{project_hours:.1f}",
            'project_pct': f"{project_pct:.0f}",
            'goal_alignment_pct': f"{goal_alignment_pct:.0f}",
            'distraction_time': distraction_time,
            'context_switches': context_switches,
            'peak_hours': peak_str,
            'top_apps': "VS Code, Chrome, Terminal",  # TODO: Calculate from data
            'habits_status': habits_status,
            'total_sessions': total_sessions,
            'coding_sessions': coding_sessions,
            'research_sessions': research_sessions,
            'avg_session_length': f"{avg_session_length:.0f}",
            'best_day': best_day[0],
            'best_day_score': f"{best_day[1]:.0f}",
            'worst_day': worst_day[0],
            'worst_day_score': f"{worst_day[1]:.0f}",
            'best_time': peak_str,
            'blockers_count': blockers_count
        }
    
    def _format_prompt(self, week_data: Dict) -> str:
        """Format the prompt with week data."""
        return self.WEEKLY_REVIEW_PROMPT.format(**week_data)
    
    def _generate_fallback_review(self, week_data: Dict) -> str:
        """Generate a simple review when LLM is unavailable."""
        return f"""**Your Week in Review ({week_data['week_start']} - {week_data['week_end']})**

🎯 **Top Accomplishments:**
1. Worked {week_data['total_hours']}h this week ({week_data['change_vs_last_week']}% change)
2. Maintained {week_data['goal_alignment_pct']}% goal alignment
3. Peak productivity at {week_data['peak_hours']}

⚠️ **Areas for Improvement:**
1. {week_data['context_switches']} context switches - try batching similar tasks
2. {week_data['worst_day']} was least productive - investigate why

💡 **Key Insight:**
Your best work happens at {week_data['peak_hours']} - schedule important tasks then.

📅 **Next Week:**
Focus on reducing distractions (currently {week_data['distraction_time']}) and maintaining momentum.
"""


def get_llm_weekly_review(db_connection):
    """Get LLM weekly review instance."""
    return LLMWeeklyReview(db_connection)
