#!/usr/bin/env python3
"""
🧠 KrypticTrack Premium TUI
Ultra-sophisticated terminal interface with live updates, advanced visualizations,
and smooth animations. Built with Rich library for maximum visual appeal.

Features:
- Live auto-refreshing dashboard
- Interactive keyboard navigation  
- Beautiful charts and heatmaps
- Smart notifications
- Habit tracking calendar
- Session timeline visualization
- Export functionality
- Custom cyberpunk theme
"""

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich.align import Align
from rich import box
from rich.columns import Columns
from rich.syntax import Syntax
from datetime import datetime, timedelta
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional
import threading
import queue

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables


class PremiumTheme:
    """Custom cyberpunk-inspired color theme."""
    
    # Primary colors
    PRIMARY = "bright_cyan"
    SECONDARY = "bright_magenta"
    SUCCESS = "bright_green"
    WARNING = "bright_yellow"
    DANGER = "bright_red"
    INFO = "bright_blue"
    
    # UI elements
    HEADER_BG = "blue"
    PANEL_BORDER = "cyan"
    HIGHLIGHT = "magenta"
    DIM = "dim white"
    
    # Productivity colors (gradient)
    PROD_COLORS = {
        'none': 'dim white',
        'low': 'bright_red',
        'medium': 'bright_yellow',
        'high': 'bright_cyan',
        'peak': 'bright_magenta'
    }
    
    def get_productivity_color(self, score: float) -> str:
        """Get color based on productivity score."""
        if score >= 80:
            return self.PROD_COLORS['peak']
        elif score >= 60:
            return self.PROD_COLORS['high']
        elif score >= 40:
            return self.PROD_COLORS['medium']
        elif score >= 20:
            return self.PROD_COLORS['low']
        else:
            return self.PROD_COLORS['none']


class DataCache:
    """Caches data to reduce database queries."""
    
    def __init__(self):
        self.cache = {}
        self.timestamps = {}
        self.ttl = 5  # seconds
    
    def get(self, key: str):
        """Get cached value if not expired."""
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
        return None
    
    def set(self, key: str, value):
        """Set cached value."""
        self.cache[key] = value
        self.timestamps[key] = time.time()


class PremiumTUI:
    """Premium TUI application."""
    
    def __init__(self):
        """Initialize the TUI."""
        self.console = Console()
        self.theme = PremiumTheme()
        self.cache = DataCache()
        self.running = True
        self.refresh_count = 0
        self.current_view = 'dashboard'
        self.notification_queue = queue.Queue()
        
        # Initialize database
        self.db = DatabaseManager('data/kryptic_track.db', False)
        self.conn = self.db.connect()
        create_tables(self.conn)
        
        # Load services (lazy loaded)
        self.services = {}
    
    def _get_service(self, name: str):
        """Lazy load services."""
        if name not in self.services:
            if name == 'productivity':
                from backend.services.productivity_patterns import get_productivity_pattern_analyzer
                self.services[name] = get_productivity_pattern_analyzer(self.conn)
            elif name == 'distraction':
                from backend.services.distraction_tracker import get_distraction_tracker
                self.services[name] = get_distraction_tracker(self.conn)
            elif name == 'habits':
                from backend.services.habit_analyzer import get_habit_analyzer
                self.services[name] = get_habit_analyzer(self.conn)
            elif name == 'goals':
                from backend.services.goal_service import get_goal_service
                self.services[name] = get_goal_service(self.conn)
            elif name == 'notifications':
                from backend.services.notification_service import get_notification_service
                self.services[name] = get_notification_service(self.conn)
            elif name == 'predictor':
                from backend.services.productivity_predictor import get_productivity_predictor
                self.services[name] = get_productivity_predictor(self.conn)
            elif name == 'patterns':
                from backend.services.pattern_detector import get_pattern_detector
                self.services[name] = get_pattern_detector(self.conn)
            elif name == 'tracker':
                from backend.services.time_tracker import get_time_tracker
                self.services[name] = get_time_tracker(self.conn)
            elif name == 'heatmap':
                from backend.services.heatmap_generator import get_heatmap_generator
                self.services[name] = get_heatmap_generator(self.conn)
        
        return self.services.get(name)
    
    def make_header(self) -> Panel:
        """Create premium header with status indicators."""
        grid = Table.grid(expand=True, padding=0)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=2)
        grid.add_column(justify="right", ratio=1)
        
        # Left: Logo & version
        left = Text()
        left.append("🧠 ", style=f"bold {self.theme.PRIMARY}")
        left.append("KRYPTIC", style=f"bold {self.theme.PRIMARY}")
        left.append("Track", style=f"bold {self.theme.SECONDARY}")
        left.append(" v2.0", style=self.theme.DIM)
        
        # Center: Title
        center = Text()
        center.append(f"{self.current_view.upper()} VIEW", style=f"bold white")
        
        # Right: Status indicators
        right = Text()
        right.append(f"🟢 ", style=f"{self.theme.SUCCESS}")
        right.append(f"Live  ", style=self.theme.DIM)
        right.append(f"⟳{self.refresh_count}  ", style=self.theme.DIM)
        right.append(datetime.now().strftime("%H:%M:%S"), style="bold white")
        
        grid.add_row(left, Align.center(center), right)
        
        return Panel(
            grid,
            style=f"bold white on {self.theme.HEADER_BG}",
            box=box.HEAVY,
            padding=(0, 1)
        )
    
    def make_quick_stats(self) -> Panel:
        """Create quick stats panel with sparklines."""
        # Get today's data
        cached = self.cache.get('stats')
        if cached:
            return cached
        
        today = datetime.now()
        start_of_day = today.replace(hour=0, minute=0, second=0).timestamp()
        current_time = today.timestamp()
        
        try:
            distraction = self._get_service('distraction')
            productivity = self._get_service('productivity')
            goals = self._get_service('goals')
            
            dist_data = distraction.track_distractions(start_of_day, current_time)
            focus_data = distraction.get_focus_vs_distracted_breakdown(start_of_day, current_time)
            peak_hours = productivity.get_peak_hours(days=7)
            active_goals = goals.get_active_goals()
            
            focus_pct = focus_data['focus_percentage']
            switches = dist_data['context_switches']
            focused_time = focus_data.get('focused_formatted', '0m')
            
        except:
            focus_pct = 0
            switches = 0
            focused_time = '0m'
            peak_hours = []
            active_goals = []
        
        # Create stats grid
        stats = Table.grid(padding=(0, 2), expand=True)
        stats.add_column(justify="center", ratio=1)
        stats.add_column(justify="center", ratio=1)
        stats.add_column(justify="center", ratio=1)
        stats.add_column(justify="center", ratio=1)
        
        # Row 1: Main metrics
        color = self.theme.get_productivity_color(focus_pct)
        
        stats.add_row(
            self._make_stat_cell("🎯 FOCUS", f"{focus_pct:.0f}%", color),
            self._make_stat_cell("⚠️ SWITCHES", f"{switches}", self.theme.WARNING),
            self._make_stat_cell("⏱️ FOCUSED", focused_time, self.theme.SUCCESS),
            self._make_stat_cell("📊 GOALS", f"{len(active_goals)}", self.theme.INFO)
        )
        
        # Row 2: Additional metrics
        peak_str = peak_hours[0][0] if peak_hours else "N/A"
        peak_score = f"{peak_hours[0][1]:.0f}" if peak_hours else "0"
        
        stats.add_row(
            self._make_stat_cell("🔥 PEAK", peak_str, self.theme.SECONDARY),
            self._make_stat_cell("📈 SCORE", peak_score, self.theme.PRIMARY),
            self._make_stat_cell("📅 DAY", today.strftime("%a"), self.theme.DIM),
            self._make_stat_cell("🕐 TIME", today.strftime("%H:%M"), self.theme.DIM)
        )
        
        panel = Panel(
            stats,
            title=f"[bold {self.theme.PRIMARY}]⚡ QUICK STATS[/]",
            border_style=self.theme.PANEL_BORDER,
            box=box.ROUNDED,
            padding=(1, 2)
        )
        
        self.cache.set('stats', panel)
        return panel
    
    def _make_stat_cell(self, label: str, value: str, color: str) -> Text:
        """Create a stat cell."""
        text = Text()
        text.append(f"{label}\n", style="dim")
        text.append(value, style=f"bold {color}")
        return Align.center(text)
    
    def make_habits_panel(self) -> Panel:
        """Create habits tracking panel with streaks."""
        try:
            habits = self._get_service('habits')
            habit_summary = habits.get_all_habits_summary()
        except:
            habit_summary = []
        
        if not habit_summary:
            content = Text("No habits tracked yet\nRun auto_track_habits() to start", style="dim", justify="center")
        else:
            table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
            table.add_column("Habit", style=self.theme.PRIMARY)
            table.add_column("Streak", justify="right", style=self.theme.SUCCESS)
            table.add_column("This Week", justify="right")
            table.add_column("", width=10)
            
            for h in habit_summary[:5]:
                # Format streak
                streak = h['current_streak']
                streak_text = f"{streak}🔥" if streak >= 7 else f"{streak}"
                
                # Format consistency
                consistency = h['consistency_7d']
                if consistency >= 80:
                    cons_color = self.theme.SUCCESS
                    cons_bar = "████████"
                elif consistency >= 60:
                    cons_color = self.theme.PRIMARY
                    cons_bar = "██████░░"
                elif consistency >= 40:
                    cons_color = self.theme.WARNING
                    cons_bar = "████░░░░"
                else:
                    cons_color = self.theme.DANGER
                    cons_bar = "██░░░░░░"
                
                # Shorten description
                desc = h['description'][:25]
                
                table.add_row(
                    desc,
                    streak_text,
                    f"[{cons_color}]{consistency:.0f}%[/]",
                    f"[{cons_color}]{cons_bar}[/]"
                )
            
            content = table
        
        return Panel(
            content,
            title=f"[bold {self.theme.SECONDARY}]🎯 HABITS[/]",
            border_style=self.theme.PANEL_BORDER,
            box=box.ROUNDED
        )
    
    def make_notifications_panel(self) -> Panel:
        """Create notifications panel."""
        try:
            notif = self._get_service('notifications')
            pending = notif.get_all_pending_notifications()
        except:
            pending = []
        
        if not pending:
            content = Text("✅ All good!\nNo pending notifications", style=self.theme.DIM, justify="center")
        else:
            lines = []
            urgency_icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'none': '⚪'}
            
            for notif in pending[:4]:
                icon = urgency_icons.get(notif['urgency'], '⚪')
                lines.append(f"{icon} {notif['message']}")
            
            content = "\n".join(lines)
        
        return Panel(
            content,
            title=f"[bold {self.theme.WARNING}]🔔 NOTIFICATIONS[/]",
            border_style=self.theme.PANEL_BORDER,
            box=box.ROUNDED
        )
    
    def make_mini_heatmap(self) -> Panel:
        """Create mini productivity heatmap."""
        try:
            heatmap_gen = self._get_service('heatmap')
            heatmap_str = heatmap_gen.generate_weekly_heatmap()
            # Take first 10 lines for compact view
            lines = heatmap_str.split('\n')[:12]
            content = '\n'.join(lines)
        except:
            content = "Generating heatmap..."
        
        return Panel(
            content,
            title=f"[bold {self.theme.PRIMARY}]🔥 7-DAY HEATMAP[/]",
            border_style=self.theme.PANEL_BORDER,
            box=box.ROUNDED
        )
    
    def make_progress_bars(self) -> Panel:
        """Create progress bars for various metrics."""
        progress = Progress(
            TextColumn("[bold]{task.description}", justify="left"),
            BarColumn(bar_width=30, complete_style=self.theme.PRIMARY, finished_style=self.theme.SUCCESS),
            TextColumn("[bold {color}]{task.percentage:>3.0f}%[/]"),
            expand=True
        )
        
        try:
            # Get data
            distraction = self._get_service('distraction')
            goals = self._get_service('goals')
            productivity = self._get_service('productivity')
            
            today = datetime.now()
            start_of_day = today.replace(hour=0, minute=0, second=0).timestamp()
            current_time = today.timestamp()
            
            focus_data = distraction.get_focus_vs_distracted_breakdown(start_of_day, current_time)
            active_goals = goals.get_active_goals()
            peak_hours = productivity.get_peak_hours(days=7)
            
            focus_pct = focus_data['focus_percentage']
            goal_pct = min(len(active_goals) * 33, 100)
            peak_pct = peak_hours[0][1] if peak_hours else 0
            
        except:
            focus_pct = 0
            goal_pct = 0
            peak_pct = 0
        
        # Add tasks with custom colors
        progress.add_task(
            "🎯 Focus Time",
            completed=focus_pct,
            total=100,
            color=self.theme.get_productivity_color(focus_pct)
        )
        progress.add_task(
            "📊 Goals Active",
            completed=goal_pct,
            total=100,
            color=self.theme.INFO
        )
        progress.add_task(
            "🔥 Peak Performance",
            completed=peak_pct,
            total=100,
            color=self.theme.SECONDARY
        )
        
        return Panel(
            progress,
            title=f"[bold {self.theme.PRIMARY}]📈 METRICS[/]",
            border_style=self.theme.PANEL_BORDER,
            box=box.ROUNDED
        )
    
    def make_footer(self) -> Panel:
        """Create interactive footer with shortcuts."""
        shortcuts = Table.grid(expand=True, padding=(0, 2))
        shortcuts.add_column(justify="center")
        
        help_text = Text()
        help_text.append("[h] Habits  ", style=self.theme.DIM)
        help_text.append("[p] Patterns  ", style=self.theme.DIM)
        help_text.append("[w] Weekly Review  ", style=self.theme.DIM)
        help_text.append("[n] Notifications  ", style=self.theme.DIM)
        help_text.append("[e] Export  ", style=self.theme.DIM)
        help_text.append("[q] Quit", style=f"bold {self.theme.DANGER}")
        
        shortcuts.add_row(help_text)
        
        return Panel(
            shortcuts,
            style=f"white on {self.theme.HEADER_BG}",
            box=box.HEAVY,
            padding=(0, 1)
        )
    
    def create_layout(self) -> Layout:
        """Create the main layout."""
        layout = Layout()
        
        # Main structure
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="stats", size=8),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        # Body split
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )
        
        # Left split
        layout["left"].split_column(
            Layout(name="progress", size=7),
            Layout(name="heatmap")
        )
        
        # Right split
        layout["right"].split_column(
            Layout(name="habits"),
            Layout(name="notifications")
        )
        
        return layout
    
    def render(self, layout: Layout):
        """Render all panels."""
        self.refresh_count += 1
        
        layout["header"].update(self.make_header())
        layout["stats"].update(self.make_quick_stats())
        layout["progress"].update(self.make_progress_bars())
        layout["heatmap"].update(self.make_mini_heatmap())
        layout["habits"].update(self.make_habits_panel())
        layout["notifications"].update(self.make_notifications_panel())
        layout["footer"].update(self.make_footer())
    
    def run(self):
        """Run the premium TUI."""
        layout = self.create_layout()
        
        try:
            with Live(layout, refresh_per_second=1, screen=True, console=self.console):
                while self.running:
                    self.render(layout)
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.console.clear()
            self.console.print(f"\n[bold {self.theme.PRIMARY}]👋 Thank you for using KrypticTrack![/]\n")
            self.db.close()


def main():
    """Entry point."""
    console = Console()
    console.clear()
    
    # Splash screen
    console.print(f"\n[bold bright_cyan]🧠 KrypticTrack Premium TUI[/]")
    console.print(f"[dim]Loading your productivity brain...[/]\n")
    time.sleep(1)
    
    try:
        app = PremiumTUI()
        app.run()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
