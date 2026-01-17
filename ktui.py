#!/usr/bin/env python3
"""
🧠 KrypticTrack TUI (ktui)

Professional-grade terminal interface inspired by htop, fzf, ranger, and cmus.
Features live monitoring, fuzzy search, vim navigation, and beautiful visualizations.

Keyboard Shortcuts:
  1-6: Switch views (Dashboard, Sessions, Habits, Goals, Insights, Export)
  /  : Search mode
  j/k: Navigate down/up (vim style)
  h/l: Navigate left/right
  q  : Quit
  ?  : Help
  r  : Refresh data
  f  : Toggle filter
  s  : Sort options
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
from collections import defaultdict

# Rich imports
from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich import box
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.columns import Columns
from rich.align import Align

# Add project root
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables


class Theme:
    """Color theme inspired by htop/gtop."""
    # Status colors
    ACTIVE = "bright_green"
    WARNING = "bright_yellow"
    ERROR = "bright_red"
    INFO = "bright_cyan"
    DIM = "dim white"
    
    # Productivity gradient
    PROD_PEAK = "bright_magenta"
    PROD_HIGH = "bright_cyan"
    PROD_MED = "bright_yellow"
    PROD_LOW = "bright_red"
    
    # UI elements
    HEADER = "bold white on blue"
    BORDER = "cyan"
    SELECTED = "reverse"
    FOOTER = "white on blue"


class KrypticTUI:
    """Main TUI application."""
    
    VIEWS = ['dashboard', 'sessions', 'habits', 'goals', 'insights', 'export']
    
    def __init__(self):
        self.console = Console()
        self.current_view = 'dashboard'
        self.selected_index = 0
        self.search_mode = False
        self.search_query = ""
        self.filter_active = False
        self.sort_by = 'time'
        self.refresh_count = 0
        self.running = True
        
        # Initialize database
        self.db = DatabaseManager('data/kryptic_track.db', False)
        self.conn = self.db.connect()
        create_tables(self.conn)
        
        # Lazy-loaded services
        self._services = {}
    
    def _service(self, name: str):
        """Lazy load services."""
        if name not in self._services:
            if name == 'productivity':
                from backend.services.productivity_patterns import get_productivity_pattern_analyzer
                self._services[name] = get_productivity_pattern_analyzer(self.conn)
            elif name == 'distraction':
                from backend.services.distraction_tracker import get_distraction_tracker
                self._services[name] = get_distraction_tracker(self.conn)
            elif name == 'habits':
                from backend.services.habit_analyzer import get_habit_analyzer
                self._services[name] = get_habit_analyzer(self.conn)
            elif name == 'goals':
                from backend.services.goal_service import get_goal_service
                self._services[name] = get_goal_service(self.conn)
            elif name == 'notifications':
                from backend.services.notification_service import get_notification_service
                self._services[name] = get_notification_service(self.conn)
            elif name == 'predictor':
                from backend.services.productivity_predictor import get_productivity_predictor
                self._services[name] = get_productivity_predictor(self.conn)
            elif name == 'patterns':
                from backend.services.pattern_detector import get_pattern_detector
                self._services[name] = get_pattern_detector(self.conn)
            elif name == 'tracker':
                from backend.services.time_tracker import get_time_tracker
                self._services[name] = get_time_tracker(self.conn)
            elif name == 'heatmap':
                from backend.services.heatmap_generator import get_heatmap_generator
                self._services[name] = get_heatmap_generator(self.conn)
            elif name == 'sessions':
                from backend.services.session_detector import get_session_detector
                self._services[name] = get_session_detector(self.conn)
        
        return self._services.get(name)
    
    # ============================================================================
    # HEADER & FOOTER
    # ============================================================================
    
    def make_header(self) -> Panel:
        """Create header bar (htop-style)."""
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=2, justify="center")
        grid.add_column(ratio=1, justify="right")
        
        # Left: Logo
        left = Text()
        left.append("🧠 ", style="bold bright_cyan")
        left.append("KrypticTrack", style="bold bright_magenta")
        
        # Center: View name
        center = Text(f"[ {self.current_view.upper()} ]", style="bold white")
        
        # Right: Time & stats
        right = Text()
        right.append(f"⟳ {self.refresh_count} ", style=Theme.DIM)
        right.append(datetime.now().strftime("%H:%M:%S"), style="bold white")
        
        grid.add_row(left, center, right)
        
        return Panel(grid, style=Theme.HEADER, box=box.HEAVY, padding=(0, 1))
    
    def make_footer(self) -> Panel:
        """Create footer with shortcuts."""
        shortcuts = [
            ("1", "Dash", Theme.INFO),
            ("2", "Sessions", Theme.INFO),
            ("3", "Habits", Theme.INFO),
            ("4", "Goals", Theme.INFO),
            ("5", "Insights", Theme.INFO),
            ("6", "Export", Theme.INFO),
            ("/", "Search", Theme.WARNING),
            ("q", "Quit", Theme.ERROR)
        ]
        
        parts = []
        for key, label, color in shortcuts:
            text = Text()
            text.append(f" {key} ", style=f"bold black on {color}")
            text.append(f" {label} ", style=Theme.DIM)
            parts.append(text)
        
        return Panel(
            Columns(parts, expand=True, equal=True),
            style=Theme.FOOTER,
            box=box.HEAVY,
            padding=(0, 1)
        )
    
    # ============================================================================
    # DASHBOARD VIEW (gtop-style)
    # ============================================================================
    
    def make_dashboard(self) -> Layout:
        """Create dashboard view."""
        layout = Layout()
        layout.split_column(
            Layout(name="stats", size=12),
            Layout(name="main"),
            Layout(name="bottom", size=16)
        )
        
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )
        
        # Populate sections
        layout["stats"].update(self._make_quick_stats())
        layout["left"].update(self._make_activity_chart())
        layout["right"].update(self._make_notifications())
        layout["bottom"].update(self._make_heatmap_panel())
        
        return layout
    
    def _make_quick_stats(self) -> Panel:
        """Quick stats grid (gtop-style)."""
        today = datetime.now()
        start = today.replace(hour=0, minute=0, second=0).timestamp()
        now = today.timestamp()
        
        try:
            dist = self._service('distraction')
            prod = self._service('productivity')
            goals_svc = self._service('goals')
            
            focus_data = dist.get_focus_vs_distracted_breakdown(start, now)
            dist_data = dist.track_distractions(start, now)
            peaks = prod.get_peak_hours(days=7)
            active_goals = goals_svc.get_active_goals()
            
            focus_pct = focus_data.get('focus_percentage', 0)
            switches = dist_data.get('context_switches', 0)
            distraction_min = dist_data.get('total_distraction_minutes', 0)
            peak_time = peaks[0][0] if peaks else "N/A"
            
        except:
            focus_pct = 0
            switches = 0
            distraction_min = 0
            peak_time = "N/A"
            active_goals = []
        
        # Create meters
        table = Table.grid(padding=(0, 2), expand=True)
        table.add_column(justify="center")
        table.add_column(justify="center")
        table.add_column(justify="center")
        table.add_column(justify="center")
        
        # Row 1: Primary metrics
        table.add_row(
            self._make_meter("FOCUS", focus_pct, "%", is_percentage=True),
            self._make_meter("SWITCHES", switches, "", is_number=True),
            self._make_meter("DISTRACT", distraction_min, "m", is_number=True),
            self._make_meter("GOALS", len(active_goals), "", is_number=True)
        )
        
        # Row 2: Secondary metrics
        table.add_row(
            self._make_info_cell("PEAK HOUR", peak_time),
            self._make_info_cell("DAY", today.strftime("%A")),
            self._make_info_cell("DATE", today.strftime("%b %d")),
            self._make_info_cell("STATUS", "🟢 Active")
        )
        
        return Panel(
            table,
            title="[bold bright_cyan]⚡ LIVE METRICS[/]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )
    
    def _make_meter(self, label: str, value: float, unit: str, is_percentage: bool = False, is_number: bool = False) -> Text:
        """Create a meter widget."""
        text = Text()
        text.append(f"{label}\n", style=Theme.DIM)
        
        if is_percentage:
            if value >= 80:
                color = Theme.PROD_PEAK
                bar = "████████"
            elif value >= 60:
                color = Theme.PROD_HIGH
                bar = "██████░░"
            elif value >= 40:
                color = Theme.PROD_MED
                bar = "████░░░░"
            else:
                color = Theme.PROD_LOW
                bar = "██░░░░░░"
            
            text.append(f"{value:.0f}{unit}\n", style=f"bold {color}")
            text.append(bar, style=color)
        elif is_number:
            # Color code based on value context
            if label == "SWITCHES":
                color = Theme.ERROR if value > 50 else Theme.WARNING if value > 20 else Theme.ACTIVE
            elif label == "DISTRACT":
                color = Theme.ERROR if value > 30 else Theme.WARNING if value > 15 else Theme.ACTIVE
            else:
                color = Theme.INFO
            
            text.append(f"{int(value)}{unit}", style=f"bold {color}")
        else:
            text.append(f"{value}{unit}", style="bold white")
        
        return Align.center(text)
    
    def _make_info_cell(self, label: str, value: str) -> Text:
        """Create info cell."""
        text = Text()
        text.append(f"{label}\n", style=Theme.DIM)
        text.append(value, style="bold white")
        return Align.center(text)
    
    def _make_activity_chart(self) -> Panel:
        """Activity timeline chart."""
        today = datetime.now()
        
        # Get hourly data
        try:
            prod = self._service('productivity')
            start = today.replace(hour=0, minute=0, second=0).timestamp()
            now = today.timestamp()
            hourly = prod.analyze_hourly_productivity(start, now)
            
            # Create bar chart
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("Hour", style=Theme.DIM, width=5)
            table.add_column("Activity", width=50)
            table.add_column("Score", justify="right", width=8)
            
            current_hour = today.hour
            for hour in range(24):
                score = hourly.get(hour, 0)
                bar_len = int(score / 2)  # Max 50 chars
                
                # Color based on score
                if score >= 80:
                    color = Theme.PROD_PEAK
                elif score >= 60:
                    color = Theme.PROD_HIGH
                elif score >= 40:
                    color = Theme.PROD_MED
                elif score > 0:
                    color = Theme.PROD_LOW
                else:
                    color = Theme.DIM
                
                # Highlight current hour
                hour_style = "bold" if hour == current_hour else Theme.DIM
                bar = "█" * bar_len
                
                score_text = f"{score:.0f}" if score > 0 else ""
                
                table.add_row(
                    f"{hour:02d}:00",
                    Text(bar, style=color),
                    Text(score_text, style=color)
                )
        
        except Exception as e:
            table = Text(f"Loading activity data...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            table,
            title="[bold bright_cyan]📊 TODAY'S ACTIVITY[/]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )
    
    def _make_notifications(self) -> Panel:
        """Notifications panel."""
        try:
            notif = self._service('notifications')
            pending = notif.get_all_pending_notifications()
            
            if not pending:
                content = Text("✅ All Clear\n\nNo pending\nnotifications", style=Theme.DIM, justify="center")
            else:
                urgency_colors = {
                    'high': Theme.ERROR,
                    'medium': Theme.WARNING,
                    'low': Theme.INFO,
                    'none': Theme.DIM
                }
                urgency_icons = {
                    'high': '🔴',
                    'medium': '🟡',
                    'low': '🟢',
                    'none': '⚪'
                }
                
                lines = []
                for n in pending[:5]:
                    icon = urgency_icons.get(n['urgency'], '⚪')
                    color = urgency_colors.get(n['urgency'], Theme.DIM)
                    # Truncate long messages
                    msg = n['message'][:40] + "..." if len(n['message']) > 40 else n['message']
                    lines.append(Text(f"{icon} {msg}", style=color))
                
                content = Text("\n").join(lines)
        
        except:
            content = Text("Loading...", style=Theme.DIM)
        
        return Panel(
            content,
            title="[bold bright_yellow]🔔 ALERTS[/]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )
    
    def _make_heatmap_panel(self) -> Panel:
        """7-day heatmap panel."""
        try:
            heatmap_gen = self._service('heatmap')
            heatmap_str = heatmap_gen.generate_weekly_heatmap()
            content = heatmap_str
        except:
            content = "Generating heatmap..."
        
        return Panel(
            content,
            title="[bold bright_magenta]🔥 7-DAY PRODUCTIVITY HEATMAP[/]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )
    
    # ============================================================================
    # SESSIONS VIEW (ranger-style browser)
    # ============================================================================
    
    def make_sessions_view(self) -> Panel:
        """Sessions table view."""
        try:
            sess_svc = self._service('sessions')
            today = datetime.now().strftime('%Y-%m-%d')
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            sessions = sess_svc.get_session_summary_by_day(week_ago, today)
            
            table = Table(show_header=True, header_style="bold bright_cyan", box=box.SIMPLE_HEAD)
            table.add_column("Date", style=Theme.DIM, width=12)
            table.add_column("Project", style="bright_white", width=20)
            table.add_column("Type", width=12)
            table.add_column("Duration", justify="right", width=10)
            table.add_column("Productivity", justify="right", width=12)
            
            for i, session in enumerate(sessions[:20]):
                date_str = datetime.fromtimestamp(session.get('start_time', time.time())).strftime('%m/%d %H:%M')
                project = session.get('project', 'Unknown')[:18]
                sess_type = session.get('session_type', 'general')
                duration = session.get('duration_minutes', 0)
                productivity = session.get('productivity_score', 0)
                
                # Color code
                if productivity >= 80:
                    prod_color = Theme.PROD_PEAK
                elif productivity >= 60:
                    prod_color = Theme.PROD_HIGH
                elif productivity >= 40:
                    prod_color = Theme.PROD_MED
                else:
                    prod_color = Theme.PROD_LOW
                
                # Type color
                type_colors = {
                    'coding': Theme.ACTIVE,
                    'research': Theme.INFO,
                    'debugging': Theme.WARNING,
                    'learning': Theme.PROD_HIGH
                }
                type_color = type_colors.get(sess_type, Theme.DIM)
                
                # Highlight selected
                style = Theme.SELECTED if i == self.selected_index else ""
                
                table.add_row(
                    date_str,
                    project,
                    Text(sess_type, style=type_color),
                    f"{duration:.0f}m",
                    Text(f"{productivity:.0f}/100", style=prod_color),
                    style=style
                )
        
        except Exception as e:
            table = Text(f"Loading sessions...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            table,
            title=f"[bold bright_cyan]📋 SESSIONS (j/k to navigate)[/]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )
    
    # ============================================================================
    # HABITS VIEW
    # ============================================================================
    
    def make_habits_view(self) -> Panel:
        """Habits tracking view with calendar."""
        try:
            habits_svc = self._service('habits')
            summary = habits_svc.get_all_habits_summary()
            
            if not summary:
                return Panel(
                    Text("No habits tracked yet", style=Theme.DIM, justify="center"),
                    title="[bold bright_green]🎯 HABITS[/]",
                    border_style=Theme.BORDER
                )
            
            # Create table
            table = Table(show_header=True, header_style="bold bright_green", box=box.SIMPLE_HEAD)
            table.add_column("Habit", width=30)
            table.add_column("Current Streak", justify="right", width=15)
            table.add_column("Best Streak", justify="right", width=12)
            table.add_column("7d Consistency", justify="right", width=18)
            table.add_column("30d Consistency", justify="right", width=18)
            
            for h in summary:
                desc = h['description'][:28]
                current = h['current_streak']
                longest = h['longest_streak']
                cons_7d = h['consistency_7d']
                cons_30d = h['consistency_30d']
                
                # Streak formatting
                if current >= 7:
                    streak_text = Text(f"{current} days 🔥", style=Theme.ACTIVE)
                elif current >= 3:
                    streak_text = Text(f"{current} days", style=Theme.INFO)
                else:
                    streak_text = Text(f"{current} days", style=Theme.DIM)
                
                # Consistency bars
                def make_bar(pct):
                    filled = int(pct / 10)
                    bar = "█" * filled + "░" * (10 - filled)
                    if pct >= 80:
                        color = Theme.ACTIVE
                    elif pct >= 60:
                        color = Theme.INFO
                    elif pct >= 40:
                        color = Theme.WARNING
                    else:
                        color = Theme.ERROR
                    return Text(f"{bar} {pct:.0f}%", style=color)
                
                table.add_row(
                    desc,
                    streak_text,
                    f"{longest} days",
                    make_bar(cons_7d),
                    make_bar(cons_30d)
                )
        
        except Exception as e:
            table = Text(f"Loading habits...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            table,
            title="[bold bright_green]🎯 HABIT TRACKER[/]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )
    
    # ============================================================================
    # GOALS VIEW
    # ============================================================================
    
    def make_goals_view(self) -> Panel:
        """Goals tracking view."""
        try:
            goals_svc = self._service('goals')
            active_goals = goals_svc.get_active_goals()
            
            if not active_goals:
                return Panel(
                    Text("No active goals\nSet goals in the main menu", style=Theme.DIM, justify="center"),
                    title="[bold bright_blue]🎯 GOALS[/]"
                )
            
            table = Table(show_header=True, header_style="bold bright_blue", box=box.SIMPLE_HEAD)
            table.add_column("Goal", width=40)
            table.add_column("Progress", width=25)
            table.add_column("Deadline", width=12)
            table.add_column("Status", width=10)
            
            today = datetime.now().date()
            for goal in active_goals[:10]:
                goal_text = goal['goal_text'][:38]
                target_date = goal.get('target_date')
                
                # Calculate progress (simplified)
                progress_pct = 50  # TODO: Real calculation
                
                # Progress bar
                filled = int(progress_pct / 10)
                bar = "█" * filled + "░" * (10 - filled)
                prog_text = Text(f"{bar} {progress_pct:.0f}%", style=Theme.INFO)
                
                # Deadline
                if target_date:
                    deadline = datetime.fromtimestamp(target_date).date()
                    days_left = (deadline - today).days
                    if days_left < 0:
                        deadline_text = Text("Overdue", style=Theme.ERROR)
                    elif days_left == 0:
                        deadline_text = Text("Today!", style=Theme.WARNING)
                    elif days_left <= 3:
                        deadline_text = Text(f"{days_left}d", style=Theme.WARNING)
                    else:
                        deadline_text = Text(f"{days_left}d", style=Theme.DIM)
                else:
                    deadline_text = Text("—", style=Theme.DIM)
                
                # Status
                status = goal.get('status', 'active')
                status_colors = {
                    'active': Theme.ACTIVE,
                    'paused': Theme.WARNING,
                    'completed': Theme.INFO
                }
                status_text = Text(status, style=status_colors.get(status, Theme.DIM))
                
                table.add_row(goal_text, prog_text, deadline_text, status_text)
        
        except Exception as e:
            table = Text(f"Loading goals...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            table,
            title="[bold bright_blue]🎯 ACTIVE GOALS[/]",
            border_style=Theme.BORDER
        )
    
    # ============================================================================
    # INSIGHTS VIEW
    # ============================================================================
    
    def make_insights_view(self) -> Layout:
        """Insights and patterns view."""
        layout = Layout()
        layout.split_column(
            Layout(name="prediction", size=10),
            Layout(name="patterns", size=20),
            Layout(name="blockers")
        )
        
        layout["prediction"].update(self._make_prediction_panel())
        layout["patterns"].update(self._make_patterns_panel())
        layout["blockers"].update(self._make_blockers_panel())
        
        return layout
    
    def _make_prediction_panel(self) -> Panel:
        """Productivity prediction."""
        try:
            predictor = self._service('predictor')
            prediction = predictor.predict_today()
            break_rec = predictor.suggest_break_time()
            
            grid = Table.grid(padding=(0, 2))
            grid.add_column()
            grid.add_column()
            
            # Prediction
            score = prediction['predicted_score']
            confidence = prediction['confidence']
            reasoning = prediction['reasoning']
            
            color = Theme.PROD_PEAK if score >= 80 else Theme.PROD_HIGH if score >= 60 else Theme.PROD_MED
            
            pred_text = Text()
            pred_text.append("📈 Today's Prediction: ", style=Theme.DIM)
            pred_text.append(f"{score:.0f}/100", style=f"bold {color}")
            pred_text.append(f" ({confidence:.0%} confidence)\n", style=Theme.DIM)
            pred_text.append(f"   {reasoning}", style=Theme.DIM)
            
            # Break recommendation
            break_text = Text()
            break_text.append("⏸️  Next Break: ", style=Theme.DIM)
            break_text.append(break_rec['suggested_time'], style="bold white")
            break_text.append(f" ({break_rec['duration_minutes']}min)\n", style=Theme.DIM)
            break_text.append(f"   {break_rec['reason']}", style=Theme.DIM)
            
            grid.add_row(pred_text)
            grid.add_row(break_text)
            
            content = grid
        
        except Exception as e:
            content = Text(f"Loading predictions...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            content,
            title="[bold bright_magenta]🔮 AI PREDICTIONS[/]",
            border_style=Theme.BORDER
        )
    
    def _make_patterns_panel(self) -> Panel:
        """Work patterns."""
        try:
            patterns_svc = self._service('patterns')
            environments = patterns_svc.detect_work_environments(days=14)
            
            if not environments:
                content = Text("Not enough data for pattern detection", style=Theme.DIM)
            else:
                table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
                table.add_column("Work Environment", width=40)
                table.add_column("Productivity", justify="right", width=15)
                table.add_column("Frequency", justify="right", width=12)
                
                for env in environments[:5]:
                    apps = ", ".join(env['apps'][:3])
                    score = env['avg_productivity']
                    freq = env['frequency']
                    
                    color = Theme.PROD_PEAK if score >= 80 else Theme.PROD_HIGH if score >= 60 else Theme.PROD_MED
                    
                    table.add_row(
                        apps,
                        Text(f"{score:.0f}/100", style=color),
                        f"{freq}x"
                    )
                
                content = table
        
        except Exception as e:
            content = Text(f"Loading patterns...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            content,
            title="[bold bright_cyan]🔍 PRODUCTIVE ENVIRONMENTS[/]",
            border_style=Theme.BORDER
        )
    
    def _make_blockers_panel(self) -> Panel:
        """Productivity blockers."""
        try:
            patterns_svc = self._service('patterns')
            blockers = patterns_svc.identify_blockers(days=14)
            
            if not blockers:
                content = Text("✅ No blockers detected!", style=Theme.ACTIVE, justify="center")
            else:
                lines = []
                for blocker in blockers[:5]:
                    lines.append(Text(f"⚠️  {blocker['pattern']}", style=Theme.WARNING))
                    lines.append(Text(f"   Impact: {blocker['impact']}", style=Theme.DIM))
                    lines.append(Text(f"   Fix: {blocker['suggestion']}\n", style=Theme.INFO))
                
                content = Text("\n").join(lines)
        
        except Exception as e:
            content = Text(f"Loading blockers...\n{str(e)}", style=Theme.DIM)
        
        return Panel(
            content,
            title="[bold bright_yellow]⚠️  PRODUCTIVITY BLOCKERS[/]",
            border_style=Theme.BORDER
        )
    
    # ============================================================================
    # EXPORT VIEW
    # ============================================================================
    
    def make_export_view(self) -> Panel:
        """Export options."""
        text = Text()
        text.append("📄 EXPORT OPTIONS\n\n", style="bold bright_cyan", justify="center")
        text.append("Available formats:\n\n", style=Theme.DIM)
        text.append("1. ", style=Theme.DIM)
        text.append("Markdown Report", style="bold white")
        text.append(" - Full weekly review\n", style=Theme.DIM)
        text.append("2. ", style=Theme.DIM)
        text.append("JSON Data", style="bold white")
        text.append(" - Raw structured data\n", style=Theme.DIM)
        text.append("3. ", style=Theme.DIM)
        text.append("CSV Export", style="bold white")
        text.append(" - Spreadsheet format\n\n", style=Theme.DIM)
        text.append("Note: Use the main TUI menu\nto export reports", style=Theme.DIM, justify="center")
        
        return Panel(
            Align.center(text),
            title="[bold bright_green]📊 EXPORT DATA[/]",
            border_style=Theme.BORDER
        )
    
    # ============================================================================
    # MAIN RENDERING
    # ============================================================================
    
    def render(self) -> Layout:
        """Render current view."""
        self.refresh_count += 1
        
        # Main layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="content"),
            Layout(name="footer", size=3)
        )
        
        # Header & footer
        layout["header"].update(self.make_header())
        layout["footer"].update(self.make_footer())
        
        # Content based on view
        if self.current_view == 'dashboard':
            layout["content"].update(self.make_dashboard())
        elif self.current_view == 'sessions':
            layout["content"].update(self.make_sessions_view())
        elif self.current_view == 'habits':
            layout["content"].update(self.make_habits_view())
        elif self.current_view == 'goals':
            layout["content"].update(self.make_goals_view())
        elif self.current_view == 'insights':
            layout["content"].update(self.make_insights_view())
        elif self.current_view == 'export':
            layout["content"].update(self.make_export_view())
        
        return layout
    
    def run(self):
        """Run the TUI."""
        layout = self.render()
        
        try:
            with Live(layout, refresh_per_second=1, screen=True):
                while self.running:
                    layout = self.render()
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.console.clear()
            self.console.print(f"\n[bold bright_cyan]👋 Thanks for using KrypticTrack![/]\n")


def main():
    """Entry point."""
    console = Console()
    console.clear()
    
    # Splash
    console.print("\n[bold bright_cyan]🧠 KrypticTrack TUI[/]")
    console.print("[dim]Initializing...[/]\n")
    time.sleep(0.5)
    
    try:
        app = KrypticTUI()
        app.run()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
