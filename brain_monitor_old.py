#!/usr/bin/env python3
"""
🧠 Brain Monitor - Live Productivity Dashboard
Real-time monitoring of your laptop brain with gtop-style interface
"""

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box
from datetime import datetime, timedelta
import time
import sys
from pathlib import Path
import threading

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.productivity_patterns import get_productivity_pattern_analyzer
from backend.services.distraction_tracker import get_distraction_tracker
from backend.services.time_tracker import get_time_tracker
from backend.services.session_detector import get_session_detector
from backend.services.goal_service import get_goal_service


class BrainMonitor:
    """Real-time brain monitoring dashboard."""
    
    def __init__(self):
        self.console = Console()
        self.running = True
        self.refresh_count = 0
        
        # Initialize database
        self.db = DatabaseManager('data/kryptic_track.db', False)
        self.conn = self.db.connect()
        create_tables(self.conn)
        
        # Services
        self.analyzer = get_productivity_pattern_analyzer(self.conn)
        self.distraction = get_distraction_tracker(self.conn)
        self.tracker = get_time_tracker(self.conn)
        self.sessions = get_session_detector(self.conn)
        self.goals = get_goal_service(self.conn)
        
        # Cache
        self.cached_data = {}
        self.last_update = 0
    
    def get_today_timestamps(self):
        """Get today's start and end timestamps."""
        today = datetime.now()
        start = today.replace(hour=0, minute=0, second=0).timestamp()
        end = today.replace(hour=23, minute=59, second=59).timestamp()
        return start, end
    
    def fetch_data(self):
        """Fetch all data (cached for 5 seconds)."""
        now = time.time()
        if now - self.last_update < 5:
            return self.cached_data
        
        start, end = self.get_today_timestamps()
        
        try:
            self.cached_data = {
                'distractions': self.distraction.track_distractions(start, end),
                'focus': self.distraction.get_focus_vs_distracted_breakdown(start, end),
                'peak_hours': self.analyzer.get_peak_hours(days=7),
                'goals': self.goals.get_active_goals(),
                'hourly': self.analyzer.analyze_hourly_productivity(start, end),
            }
            self.last_update = now
        except Exception as e:
            # Fallback to empty data
            self.cached_data = {
                'distractions': {'context_switches': 0, 'total_distraction_minutes': 0, 'by_category': {}},
                'focus': {'focus_percentage': 0, 'focused_minutes': 0, 'focused_formatted': '0m'},
                'peak_hours': [],
                'goals': [],
                'hourly': {},
            }
        
        return self.cached_data
    
    def make_header(self) -> Panel:
        """Create header."""
        title = Text()
        title.append("🧠 ", style="bold cyan")
        title.append("BRAIN MONITOR", style="bold white")
        title.append(" - Real-time Productivity Dashboard", style="dim")
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        grid.add_row(
            f"[dim]Refresh #{self.refresh_count}[/]",
            title,
            f"[bold cyan]{datetime.now().strftime('%H:%M:%S')}[/]"
        )
        
        return Panel(grid, style="bold white on blue", box=box.HEAVY)
    
    def make_stats_grid(self) -> Table:
        """Create stats grid."""
        data = self.fetch_data()
        
        table = Table.grid(padding=1, expand=True)
        table.add_column(justify="center", ratio=1)
        table.add_column(justify="center", ratio=1)
        table.add_column(justify="center", ratio=1)
        table.add_column(justify="center", ratio=1)
        
        # Row 1: Main metrics
        focus_pct = data['focus']['focus_percentage']
        focus_color = "green" if focus_pct >= 70 else "yellow" if focus_pct >= 50 else "red"
        
        table.add_row(
            self._make_stat_box("🎯 FOCUS", f"{focus_pct:.0f}%", focus_color),
            self._make_stat_box("⚠️  SWITCHES", str(data['distractions']['context_switches']), "cyan"),
            self._make_stat_box("⏱️  FOCUSED", data['focus']['focused_formatted'], "green"),
            self._make_stat_box("📊 GOALS", str(len(data['goals'])), "magenta"),
        )
        
        # Row 2: Additional metrics
        if data['peak_hours']:
            peak_hour = data['peak_hours'][0][0]
            peak_score = f"{data['peak_hours'][0][1]:.0f}"
        else:
            peak_hour = "N/A"
            peak_score = "0"
        
        distracted_mins = data['distractions']['total_distraction_minutes']
        
        table.add_row(
            self._make_stat_box("🔥 PEAK", peak_hour, "yellow"),
            self._make_stat_box("📈 SCORE", peak_score, "yellow"),
            self._make_stat_box("😴 DISTRACTED", f"{distracted_mins:.0f}m", "red"),
            self._make_stat_box("💸 COST", f"{distracted_mins * 23:.0f}m", "red"),
        )
        
        return table
    
    def _make_stat_box(self, label: str, value: str, color: str = "white") -> Panel:
        """Create a stat box."""
        content = Text()
        content.append(f"{label}\n", style="dim")
        content.append(value, style=f"bold {color}")
        
        return Panel(
            content,
            border_style=color,
            box=box.ROUNDED,
            padding=(0, 1)
        )
    
    def make_progress_bars(self) -> Panel:
        """Create progress bars for categories."""
        data = self.fetch_data()
        
        progress = Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[cyan]{task.percentage:>3.0f}%"),
            expand=True
        )
        
        # Focus progress
        focus_pct = data['focus']['focus_percentage']
        progress.add_task("🎯 Focus Time", completed=focus_pct, total=100)
        
        # Goals progress (mock - based on count)
        goal_pct = min(len(data['goals']) * 33, 100)
        progress.add_task("📊 Goals Active", completed=goal_pct, total=100)
        
        # Peak hour score
        if data['peak_hours']:
            peak_pct = data['peak_hours'][0][1]
        else:
            peak_pct = 0
        progress.add_task("🔥 Peak Performance", completed=peak_pct, total=100)
        
        return Panel(progress, title="[bold]📊 Metrics", border_style="cyan", box=box.ROUNDED)
    
    def make_heatmap_mini(self) -> Panel:
        """Create mini heatmap."""
        data = self.fetch_data()
        hourly = data['hourly']
        
        # Current hour and surrounding hours
        current_hour = datetime.now().hour
        hours_to_show = range(max(0, current_hour - 5), min(24, current_hour + 2))
        
        lines = []
        lines.append("[bold]Today's Hourly Productivity[/]\n")
        
        for hour in hours_to_show:
            score = hourly.get(hour, 0)
            bar_len = int(score / 100 * 20)
            
            if score >= 75:
                bar = "[green]" + "█" * bar_len + "[/]"
                icon = "🔥"
            elif score >= 50:
                bar = "[yellow]" + "█" * bar_len + "[/]"
                icon = "💪"
            elif score >= 25:
                bar = "[cyan]" + "█" * bar_len + "[/]"
                icon = "📊"
            else:
                bar = "[dim]" + "░" * max(1, bar_len) + "[/]"
                icon = "💤"
            
            current_marker = "→ " if hour == current_hour else "   "
            lines.append(f"{current_marker}{hour:02d}:00 {icon} {bar:<30} {score:>5.1f}")
        
        return Panel(
            "\n".join(lines),
            title="[bold]📅 Activity",
            border_style="magenta",
            box=box.ROUNDED
        )
    
    def make_goals_panel(self) -> Panel:
        """Create goals panel."""
        data = self.fetch_data()
        goals = data['goals']
        
        if not goals:
            content = "[dim]No active goals set.\nUse the main TUI to add goals![/]"
        else:
            lines = []
            for i, goal in enumerate(goals[:5], 1):
                emoji = "✅" if i % 2 == 0 else "🎯"
                lines.append(f"{emoji} {goal['goal_text'][:40]}")
            content = "\n".join(lines)
        
        return Panel(
            content,
            title=f"[bold]🎯 Goals ({len(goals)})",
            border_style="green",
            box=box.ROUNDED
        )
    
    def make_distractions_panel(self) -> Panel:
        """Create distractions breakdown."""
        data = self.fetch_data()
        categories = data['distractions']['by_category']
        
        if not categories:
            content = "[green]✨ No distractions detected!\nYou're doing great![/]"
        else:
            lines = []
            emoji_map = {
                'social_media': '📱',
                'messaging': '💬',
                'entertainment': '🎮',
                'browsing': '🌐'
            }
            
            for cat, mins in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                emoji = emoji_map.get(cat, '•')
                cat_name = cat.replace('_', ' ').title()
                lines.append(f"{emoji} {cat_name}: [red]{int(mins)}m[/]")
            
            content = "\n".join(lines[:5])
        
        return Panel(
            content,
            title="[bold]⚠️  Distractions",
            border_style="red",
            box=box.ROUNDED
        )
    
    def make_footer(self) -> Panel:
        """Create footer with controls."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="center")
        
        grid.add_row(
            "[dim]Press [bold]Ctrl+C[/bold] to exit  •  Updates every second  •  Data cached 5s[/]"
        )
        
        return Panel(grid, style="white on dark_blue")
    
    def make_layout(self) -> Layout:
        """Create main layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="stats", size=8),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )
        
        layout["left"].split_column(
            Layout(name="progress", size=7),
            Layout(name="heatmap")
        )
        
        layout["right"].split_column(
            Layout(name="goals"),
            Layout(name="distractions")
        )
        
        return layout
    
    def render(self, layout: Layout):
        """Render all panels."""
        self.refresh_count += 1
        
        layout["header"].update(self.make_header())
        layout["stats"].update(self.make_stats_grid())
        layout["progress"].update(self.make_progress_bars())
        layout["heatmap"].update(self.make_heatmap_mini())
        layout["goals"].update(self.make_goals_panel())
        layout["distractions"].update(self.make_distractions_panel())
        layout["footer"].update(self.make_footer())
    
    def run(self):
        """Run the monitor."""
        layout = self.make_layout()
        
        try:
            with Live(layout, refresh_per_second=2, screen=True, console=self.console):
                while self.running:
                    self.render(layout)
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.console.clear()
            self.console.print("\n[bold cyan]👋 Brain Monitor stopped![/]\n")
            self.db.close()


def main():
    """Entry point."""
    console = Console()
    console.clear()
    console.print("[bold cyan]🧠 Starting Brain Monitor...[/]\n")
    
    try:
        monitor = BrainMonitor()
        monitor.run()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
