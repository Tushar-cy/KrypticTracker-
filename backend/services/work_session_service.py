"""Service for managing daily work sessions and analysis."""

import time
import json
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from backend.services.llm_service import get_llm_service
from backend.utils.logger import get_logger
from backend.utils.exceptions import DatabaseError, LLMServiceError

logger = get_logger("work_session")


class WorkSessionService:
    """Service for managing work sessions and daily analysis."""
    
    def __init__(self, db_connection):
        """
        Initialize work session service.
        
        Args:
            db_connection: Database connection
        """
        self.db = db_connection
        self.llm = get_llm_service()
    
    def start_work_session(self, planned_work: str) -> Dict[str, Any]:
        """
        Start a new work session for today.
        
        Args:
            planned_work: Description of what user plans to work on
            
        Returns:
            Work session data
        """
        try:
            today = date.today().isoformat()
            start_time = time.time()
            
            cursor = self.db.cursor()
            
            # Check if session already exists for today
            cursor.execute("""
                SELECT id, start_time, planned_work 
                FROM work_sessions 
                WHERE date = ? AND end_time IS NULL
            """, (today,))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing session
                cursor.execute("""
                    UPDATE work_sessions 
                    SET planned_work = ?, start_time = ?
                    WHERE id = ?
                """, (planned_work, start_time, existing[0]))
                session_id = existing[0]
            else:
                # Create new session
                cursor.execute("""
                    INSERT INTO work_sessions (date, start_time, planned_work)
                    VALUES (?, ?, ?)
                """, (today, start_time, planned_work))
                session_id = cursor.lastrowid
            
            self.db.commit()
            
            logger.info("Work session started", session_id=session_id, planned_work=planned_work)
            
            return {
                'session_id': session_id,
                'date': today,
                'start_time': start_time,
                'planned_work': planned_work,
                'status': 'active'
            }
            
        except Exception as e:
            logger.error("Failed to start work session", error=str(e))
            raise DatabaseError(f"Failed to start work session: {str(e)}")
    
    def end_work_session(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        """
        End work session and generate analysis.
        
        Args:
            session_id: Optional session ID (if None, uses today's active session)
            
        Returns:
            Analysis results
        """
        try:
            today = date.today().isoformat()
            end_time = time.time()
            
            cursor = self.db.cursor()
            
            # Get session
            if session_id:
                cursor.execute("""
                    SELECT id, date, start_time, planned_work 
                    FROM work_sessions 
                    WHERE id = ?
                """, (session_id,))
            else:
                cursor.execute("""
                    SELECT id, date, start_time, planned_work 
                    FROM work_sessions 
                    WHERE date = ? AND end_time IS NULL
                    ORDER BY start_time DESC
                    LIMIT 1
                """, (today,))
            
            session = cursor.fetchone()
            if not session:
                raise DatabaseError("No active work session found")
            
            session_id, session_date, start_time, planned_work = session
            
            # Get all actions for this day
            day_start = datetime.fromisoformat(session_date).timestamp()
            day_end = day_start + 86400  # 24 hours
            
            cursor.execute("""
                SELECT 
                    timestamp,
                    source,
                    action_type,
                    context_json
                FROM actions
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (day_start, day_end))
            
            actions = cursor.fetchall()
            
            # Analyze the day's data
            analysis = self._analyze_day(planned_work, actions, start_time, end_time)
            
            # Update session with analysis
            cursor.execute("""
                UPDATE work_sessions 
                SET 
                    end_time = ?,
                    actual_summary = ?,
                    time_wasted_minutes = ?,
                    idle_time_minutes = ?,
                    focused_time_minutes = ?,
                    distractions = ?,
                    achievements = ?,
                    insights = ?
                WHERE id = ?
            """, (
                end_time,
                analysis.get('summary', ''),
                analysis.get('time_wasted_minutes', 0),
                analysis.get('idle_time_minutes', 0),
                analysis.get('focused_time_minutes', 0),
                json.dumps(analysis.get('distractions', [])),
                json.dumps(analysis.get('achievements', [])),
                analysis.get('insights', '')
            ))
            
            self.db.commit()
            
            logger.info("Work session ended", session_id=session_id, analysis_complete=True)
            
            return {
                'session_id': session_id,
                'date': session_date,
                'start_time': start_time,
                'end_time': end_time,
                'planned_work': planned_work,
                'analysis': analysis
            }
            
        except Exception as e:
            logger.error("Failed to end work session", error=str(e))
            raise DatabaseError(f"Failed to end work session: {str(e)}")
    
    def _analyze_day(self, planned_work: str, actions: List, start_time: float, end_time: float) -> Dict[str, Any]:
        """
        Analyze a day's work using LLM and data analysis.
        
        Args:
            planned_work: What user planned to work on
            actions: List of actions for the day
            start_time: Session start time
            end_time: Session end time
            
        Returns:
            Analysis dictionary
        """
        try:
            # Calculate basic metrics
            total_duration_minutes = (end_time - start_time) / 60
            
            # Group actions by source and type
            source_counts = {}
            action_type_counts = {}
            app_usage = {}  # Track time spent in each app
            url_visits = {}  # Track time spent on each URL
            idle_periods = []
            
            last_action_time = start_time
            current_app = None
            current_url = None
            app_start_time = None
            url_start_time = None
            
            for action in actions:
                timestamp = action[0]
                source = action[1]
                action_type = action[2]
                context_json = action[3]
                
                try:
                    context = json.loads(context_json) if context_json else {}
                except:
                    context = {}
                
                # Count sources and types
                source_counts[source] = source_counts.get(source, 0) + 1
                action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1
                
                # Track app usage
                if source == 'system' and action_type in ['app_launch', 'app_switch', 'window_focus']:
                    app_name = context.get('app_name') or context.get('application_name', 'unknown')
                    if current_app and app_start_time:
                        duration = (timestamp - app_start_time) / 60
                        app_usage[current_app] = app_usage.get(current_app, 0) + duration
                    current_app = app_name
                    app_start_time = timestamp
                
                # Track URL visits
                if source == 'chrome' and action_type in ['page_visit', 'tab_switch']:
                    url = context.get('url', 'unknown')
                    if current_url and url_start_time:
                        duration = (timestamp - url_start_time) / 60
                        url_visits[current_url] = url_visits.get(current_url, 0) + duration
                    current_url = url
                    url_start_time = timestamp
                
                # Detect idle periods (gaps > 5 minutes)
                gap_minutes = (timestamp - last_action_time) / 60
                if gap_minutes > 5:
                    idle_periods.append({
                        'start': last_action_time,
                        'end': timestamp,
                        'duration_minutes': gap_minutes
                    })
                
                last_action_time = timestamp
            
            # Calculate final app/URL durations
            if current_app and app_start_time:
                duration = (end_time - app_start_time) / 60
                app_usage[current_app] = app_usage.get(current_app, 0) + duration
            
            if current_url and url_start_time:
                duration = (end_time - url_start_time) / 60
                url_visits[current_url] = url_visits.get(current_url, 0) + duration
            
            # Calculate metrics
            total_idle_minutes = sum(p['duration_minutes'] for p in idle_periods)
            total_focused_minutes = total_duration_minutes - total_idle_minutes
            
            # Identify distractions (non-work apps/URLs)
            distractions = []
            work_keywords = ['code', 'github', 'stackoverflow', 'docs', 'terminal', 'cursor', 'vscode']
            
            for app, minutes in sorted(app_usage.items(), key=lambda x: x[1], reverse=True):
                if minutes > 10:  # More than 10 minutes
                    is_work = any(keyword in app.lower() for keyword in work_keywords)
                    if not is_work and app.lower() not in ['chrome', 'firefox', 'brave']:
                        distractions.append({
                            'type': 'app',
                            'name': app,
                            'time_minutes': round(minutes, 1)
                        })
            
            for url, minutes in sorted(url_visits.items(), key=lambda x: x[1], reverse=True):
                if minutes > 10:  # More than 10 minutes
                    is_work = any(keyword in url.lower() for keyword in work_keywords)
                    if not is_work:
                        domain = url.split('/')[2] if '/' in url else url
                        distractions.append({
                            'type': 'website',
                            'name': domain,
                            'url': url,
                            'time_minutes': round(minutes, 1)
                        })
            
            # Identify achievements (work-related activities)
            achievements = []
            work_actions = ['file_edit', 'git_commit', 'terminal_command', 'code_completion']
            for action_type, count in action_type_counts.items():
                if action_type in work_actions and count > 5:
                    achievements.append({
                        'type': action_type,
                        'count': count
                    })
            
            # Generate LLM analysis
            llm_analysis = self._generate_llm_analysis(
                planned_work,
                source_counts,
                action_type_counts,
                app_usage,
                url_visits,
                idle_periods,
                distractions,
                total_duration_minutes,
                total_idle_minutes,
                total_focused_minutes
            )
            
            return {
                'summary': llm_analysis.get('summary', ''),
                'insights': llm_analysis.get('insights', ''),
                'time_wasted_minutes': round(sum(d['time_minutes'] for d in distractions), 1),
                'idle_time_minutes': round(total_idle_minutes, 1),
                'focused_time_minutes': round(total_focused_minutes, 1),
                'distractions': distractions[:10],  # Top 10
                'achievements': achievements,
                'total_actions': len(actions),
                'top_apps': sorted(app_usage.items(), key=lambda x: x[1], reverse=True)[:5],
                'top_urls': sorted(url_visits.items(), key=lambda x: x[1], reverse=True)[:5]
            }
            
        except Exception as e:
            logger.error("Failed to analyze day", error=str(e))
            # Return basic analysis without LLM
            return {
                'summary': f"Analyzed {len(actions)} actions over {round((end_time - start_time) / 60, 1)} minutes",
                'insights': 'LLM analysis unavailable',
                'time_wasted_minutes': 0,
                'idle_time_minutes': 0,
                'focused_time_minutes': 0,
                'distractions': [],
                'achievements': []
            }
    
    def _generate_llm_analysis(
        self,
        planned_work: str,
        source_counts: Dict[str, int],
        action_type_counts: Dict[str, int],
        app_usage: Dict[str, float],
        url_visits: Dict[str, float],
        idle_periods: List[Dict],
        distractions: List[Dict],
        total_duration: float,
        idle_time: float,
        focused_time: float
    ) -> Dict[str, str]:
        """
        Generate LLM-powered analysis of the work day.
        
        Returns:
            Dictionary with 'summary' and 'insights'
        """
        if not self.llm.is_available():
            return {
                'summary': 'LLM service unavailable for detailed analysis',
                'insights': ''
            }
        
        try:
            # Prepare context for LLM
            top_apps = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)[:10]
            top_urls = sorted(url_visits.items(), key=lambda x: x[1], reverse=True)[:10]
            
            prompt = f"""You are analyzing a work day. The user planned to work on: "{planned_work}"

Here's what actually happened:

**Time Breakdown:**
- Total time: {round(total_duration, 1)} minutes ({round(total_duration/60, 1)} hours)
- Focused time: {round(focused_time, 1)} minutes
- Idle time: {round(idle_time, 1)} minutes
- Time wasted on distractions: {round(sum(d['time_minutes'] for d in distractions), 1)} minutes

**Top Applications Used:**
{chr(10).join(f"- {app}: {round(minutes, 1)} minutes" for app, minutes in top_apps[:5])}

**Top Websites Visited:**
{chr(10).join(f"- {url[:60]}: {round(minutes, 1)} minutes" for url, minutes in top_urls[:5])}

**Main Distractions:**
{chr(10).join(f"- {d['name']}: {d['time_minutes']} minutes" for d in distractions[:5])}

**Idle Periods:**
{chr(10).join(f"- {round(p['duration_minutes'], 1)} minutes idle" for p in idle_periods[:3])}

**Action Types:**
{chr(10).join(f"- {action_type}: {count} times" for action_type, count in sorted(action_type_counts.items(), key=lambda x: x[1], reverse=True)[:10])}

Provide a concise, honest analysis in this format:

**Summary:** (2-3 sentences about what they actually did vs planned)

**Insights:**
- You were inclined over [place/app] for [X] minutes
- You wasted [X] minutes on [distraction]
- You were idle for [X] minutes total
- You were doing [activity] most of the time
- [Other relevant insights]

Be direct and helpful, like a coach reviewing performance."""

            response = self.llm.chat(prompt, intent='analysis')
            
            # Parse response into summary and insights
            if '**Summary:**' in response:
                parts = response.split('**Insights:**')
                summary = parts[0].replace('**Summary:**', '').strip()
                insights = parts[1].strip() if len(parts) > 1 else ''
            else:
                summary = response[:200] + '...' if len(response) > 200 else response
                insights = response
            
            return {
                'summary': summary,
                'insights': insights
            }
            
        except Exception as e:
            logger.error("LLM analysis failed", error=str(e))
            return {
                'summary': 'Analysis generated but LLM details unavailable',
                'insights': ''
            }
    
    def get_today_session(self) -> Optional[Dict[str, Any]]:
        """Get today's work session if it exists."""
        try:
            today = date.today().isoformat()
            cursor = self.db.cursor()
            
            cursor.execute("""
                SELECT 
                    id, date, start_time, end_time, planned_work,
                    actual_summary, time_wasted_minutes, idle_time_minutes,
                    focused_time_minutes, distractions, achievements, insights
                FROM work_sessions
                WHERE date = ?
                ORDER BY start_time DESC
                LIMIT 1
            """, (today,))
            
            session = cursor.fetchone()
            if not session:
                return None
            
            return {
                'session_id': session[0],
                'date': session[1],
                'start_time': session[2],
                'end_time': session[3],
                'planned_work': session[4],
                'actual_summary': session[5],
                'time_wasted_minutes': session[6],
                'idle_time_minutes': session[7],
                'focused_time_minutes': session[8],
                'distractions': json.loads(session[9]) if session[9] else [],
                'achievements': json.loads(session[10]) if session[10] else [],
                'insights': session[11],
                'status': 'completed' if session[3] else 'active'
            }
            
        except Exception as e:
            logger.error("Failed to get today's session", error=str(e))
            return None

