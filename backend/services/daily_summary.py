"""
Daily Summary Generator

Generates comprehensive, LLM-narrated daily summaries combining:
- Session detection
- Time tracking
- Action analysis
- Goal alignment
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import time

from backend.services.session_detector import get_session_detector
from backend.services.time_tracker import get_time_tracker
from backend.services.goal_service import get_goal_service
from backend.services.llm_service import get_llm_service


class DailySummaryGenerator:
    """Generates rich daily summaries with LLM narration."""
    
    def __init__(self, db_connection):
        """Initialize daily summary generator."""
        self.db = db_connection
        self.session_detector = get_session_detector(db_connection)
        self.time_tracker = get_time_tracker(db_connection)
        self.goal_service = get_goal_service(db_connection)
        self.llm = get_llm_service()
    
    def generate_summary(self, date: str, use_llm: bool = True) -> Dict:
        """
        Generate complete daily summary.
        
        Args:
            date: Date string in 'YYYY-MM-DD' format
            use_llm: Whether to use LLM for narrative generation
        
        Returns:
            Complete summary dictionary
        """
        # Get time range for the day
        dt = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        # Gather all data
        sessions = self.session_detector.detect_sessions(start_of_day, end_of_day)
        time_breakdown = self.time_tracker.get_daily_breakdown(date)
        active_goals = self.goal_service.get_active_goals()
        
        # Calculate goal alignments
        goal_alignments = []
        for goal in active_goals:
            alignment = self.goal_service.check_alignment(goal['id'], start_of_day, end_of_day)
            if alignment.get('relevant_actions', 0) > 0:
                feedback = self.goal_service.generate_feedback(goal['id'], 'day')
                goal_alignments.append({
                    'goal': goal['goal_text'],
                    'alignment': alignment,
                    'feedback': feedback
                })
        
        # Get action statistics
        stats = self._get_action_stats(start_of_day, end_of_day)
        
        # Build structured summary
        structured_summary = {
            'date': date,
            'total_time': time_breakdown['total_time'],
            'sessions': {
                'count': len(sessions),
                'by_type': self._group_sessions_by_type(sessions),
                'top_projects': self._get_top_projects(sessions)
            },
            'time_breakdown': {
                'by_app': time_breakdown['by_app'][:5],  # Top 5 apps
                'by_project': time_breakdown['by_project'][:5],  # Top 5 projects
                'by_activity': time_breakdown['by_activity']
            },
            'productivity': {
                'deep_work_periods': time_breakdown['deep_work_periods'],
                'context_switches': time_breakdown['context_switches'],
                'focus_score': self._calculate_focus_score(time_breakdown)
            },
            'goals': goal_alignments,
            'statistics': stats
        }
        
        # Generate LLM narrative if requested
        if use_llm and self.llm.is_available():
            try:
                narrative = self._generate_llm_narrative(structured_summary)
                structured_summary['narrative'] = narrative
            except Exception as e:
                print(f"LLM narration failed: {e}")
                structured_summary['narrative'] = self._generate_fallback_narrative(structured_summary)
        else:
            structured_summary['narrative'] = self._generate_fallback_narrative(structured_summary)
        
        return structured_summary
    
    def _get_action_stats(self, start_time: float, end_time: float) -> Dict:
        """Get action statistics for the day."""
        cursor = self.db.cursor()
        
        # Total actions
        cursor.execute("""
            SELECT COUNT(*) FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
        """, (start_time, end_time))
        total_actions = cursor.fetchone()[0]
        
        # Actions by source
        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY source
            ORDER BY count DESC
        """, (start_time, end_time))
        by_source = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Top action types
        cursor.execute("""
            SELECT action_type, COUNT(*) as count
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY action_type
            ORDER BY count DESC
            LIMIT 10
        """, (start_time, end_time))
        top_actions = [{'type': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # Git commits
        cursor.execute("""
            SELECT COUNT(*) FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            AND action_type = 'git_commit'
        """, (start_time, end_time))
        git_commits = cursor.fetchone()[0]
        
        # Terminal commands
        cursor.execute("""
            SELECT COUNT(*) FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            AND action_type IN ('terminal_command', 'npm_history_command', 'pip_history_command')
        """, (start_time, end_time))
        terminal_commands = cursor.fetchone()[0]
        
        return {
            'total_actions': total_actions,
            'by_source': by_source,
            'top_actions': top_actions,
            'git_commits': git_commits,
            'terminal_commands': terminal_commands
        }
    
    def _group_sessions_by_type(self, sessions: List[Dict]) -> Dict:
        """Group sessions by type and calculate total time."""
        grouped = {}
        for session in sessions:
            session_type = session['session_type']
            if session_type not in grouped:
                grouped[session_type] = {
                    'count': 0,
                    'total_minutes': 0,
                    'total_seconds': 0,
                    'sessions': []
                }
            grouped[session_type]['count'] += 1
            # Use duration directly from session
            duration_seconds = session.get('duration_seconds', session['duration_minutes'] * 60)
            grouped[session_type]['total_seconds'] += duration_seconds
            grouped[session_type]['total_minutes'] += duration_seconds / 60
            grouped[session_type]['sessions'].append(session)
        return grouped
    
    def _get_top_projects(self, sessions: List[Dict], limit: int = 5) -> List[Dict]:
        """Get top projects by time spent."""
        project_time = {}
        for session in sessions:
            project = session['project']
            if project:
                if project not in project_time:
                    project_time[project] = 0
                project_time[project] += session['duration_minutes']
        
        # Sort by time and return top N
        sorted_projects = sorted(project_time.items(), key=lambda x: x[1], reverse=True)
        return [
            {'project': proj, 'minutes': mins, 'hours': round(mins / 60, 2)}
            for proj, mins in sorted_projects[:limit]
        ]
    
    def _calculate_focus_score(self, time_breakdown: Dict) -> float:
        """
        Calculate focus score (0-100) based on:
        - Deep work time
        - Context switches
        - Activity distribution
        """
        total_minutes = time_breakdown['total_time'].get('minutes', 0)
        if total_minutes == 0:
            return 0.0
        
        # Deep work component (0-50 points)
        deep_work_minutes = sum(
            period['duration_minutes']
            for period in time_breakdown['deep_work_periods']
        )
        deep_work_score = min(50, (deep_work_minutes / total_minutes) * 100)
        
        # Context switch component (0-30 points, inverse)
        switches = time_breakdown['context_switches']
        # Penalize frequent switches (> 1 per 10 minutes is bad)
        expected_switches = total_minutes / 10
        switch_ratio = max(0, 1 - (switches / max(expected_switches, 1)))
        switch_score = switch_ratio * 30
        
        # Activity focus component (0-20 points)
        # Higher score if time is concentrated in fewer activities
        activities = time_breakdown['by_activity']
        if activities:
            # Calculate entropy-like metric
            total_time_sec = sum(act.get('seconds', 0) for act in activities.values())
            if total_time_sec > 0:
                proportions = [act.get('seconds', 0) / total_time_sec for act in activities.values()]
                concentration = max(proportions) if proportions else 0
                activity_score = concentration * 20
            else:
                activity_score = 0
        else:
            activity_score = 0
        
        return round(deep_work_score + switch_score + activity_score, 1)
    
    def _generate_llm_narrative(self, summary: Dict) -> str:
        """Generate narrative summary using LLM."""
        # Build prompt with all the data
        prompt = self._build_summary_prompt(summary)
        
        # Get LLM response
        response = self.llm.chat(
            prompt,
            intent='reflection',
            context={'type': 'daily_summary'}
        )
        
        return response
    
    def _build_summary_prompt(self, summary: Dict) -> str:
        """Build detailed prompt for LLM."""
        date = summary['date']
        total_time = summary['total_time']
        sessions = summary['sessions']
        time_breakdown = summary['time_breakdown']
        productivity = summary['productivity']
        goals = summary['goals']
        stats = summary['statistics']
        
        prompt = f"""Generate a comprehensive daily summary for {date}.

## Time Overview
- Total active time: {total_time.get('formatted', 'N/A')}
- Sessions: {sessions['count']} work sessions
- Context switches: {productivity['context_switches']}
- Focus score: {productivity['focus_score']}/100

## Sessions by Type
"""
        for session_type, data in sessions['by_type'].items():
            prompt += f"- {session_type.title()}: {data['count']} sessions, {data['total_minutes']:.0f} minutes\n"
        
        prompt += "\n## Top Projects\n"
        for proj in sessions['top_projects'][:3]:
            prompt += f"- {proj['project']}: {proj['hours']}h\n"
        
        prompt += "\n## Time by App (Top 3)\n"
        for app in time_breakdown['by_app'][:3]:
            prompt += f"- {app['app']}: {app.get('formatted', app.get('hours', 0))}h\n"
        
        prompt += f"\n## Activity\n"
        prompt += f"- Git commits: {stats.get('git_commits', 0)}\n"
        prompt += f"- Terminal commands: {stats.get('terminal_commands', 0)}\n"
        prompt += f"- Total actions logged: {stats.get('total_actions', 0)}\n"
        
        if productivity['deep_work_periods']:
            prompt += f"\n## Deep Work\n"
            prompt += f"- {len(productivity['deep_work_periods'])} deep work periods\n"
            longest = max(productivity['deep_work_periods'], key=lambda x: x['duration_minutes'])
            prompt += f"- Longest: {longest['duration_minutes']:.0f} min on {longest.get('project', 'unknown')}\n"
        
        if goals:
            prompt += "\n## Goal Alignment\n"
            for goal_info in goals:
                prompt += f"- {goal_info['feedback']}\n"
        
        prompt += """

Generate a narrative summary that:
1. Starts with a one-sentence overview of the day
2. Breaks down major activities (coding, research, etc.) with time spent
3. Highlights key projects worked on
4. Mentions productivity patterns (deep work, focus, context switches)
5. Notes goal alignment if applicable
6. Ends with a brief reflection or insight

Keep it under 250 words, use emojis  sparingly for visual clarity, and write in second person ("you").
"""
        
        return prompt
    
    def _generate_fallback_narrative(self, summary: Dict) -> str:
        """Generate simple text narrative without LLM."""
        date = summary['date']
        total_time = summary['total_time']
        sessions = summary['sessions']
        time_breakdown = summary['time_breakdown']
        stats = summary['statistics']
        
        lines = [f"# Daily Summary for {date}\n"]
        
        lines.append(f"**Total Active Time**: {total_time.get('formatted', 'N/A')}\n")
        
        if sessions['by_type']:
            lines.append("\n## Sessions")
            for session_type, data in sessions['by_type'].items():
                lines.append(f"- **{session_type.title()}**: {data['count']} sessions, {data['total_minutes']:.0f} min")
        
        if sessions['top_projects']:
            lines.append("\n## Top Projects")
            for proj in sessions['top_projects'][:3]:
                lines.append(f"- {proj['project']}: {proj['hours']}h")
        
        if time_breakdown['by_app']:
            lines.append("\n## Time by App")
            for app in time_breakdown['by_app'][:5]:
                lines.append(f"- {app['app']}: {app.get('formatted', str(app.get('hours', 0)) + 'h')}")
        
        lines.append(f"\n## Statistics")
        lines.append(f"- Git commits: {stats.get('git_commits', 0)}")
        lines.append(f"- Terminal commands: {stats.get('terminal_commands', 0)}")
        lines.append(f"- Total actions: {stats.get('total_actions', 0)}")
        
        return '\n'.join(lines)


def get_daily_summary_generator(db_connection):
    """Get daily summary generator instance."""
    return DailySummaryGenerator(db_connection)
