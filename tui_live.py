"""
KrypticTrack Live TUI - Interactive Dashboard
Inspired by gtop and other system monitors
"""

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.text import Text
from rich import box
from datetime import datetime, timedelta
import time
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.productivity_patterns import get_productivity_pattern_analyzer
from backend.services.distraction_tracker import get_distraction_tracker
from backend.services.time_tracker import get_time_tracker
from backend.services.session_detector import get_session_detector
from backend.services.goal_service import get_goal_service


class LiveProductivityDashboard:
    """Live updating productivity dashboard."""
    
    def __init__(self):
        self.console = Console()
        self.db = DatabaseManager('data/kryptic_track.db', False)
        self.conn = self.db.connect()
        create_tables(self.conn)
        
        # Services
        self.analyzer = get_productivity_pattern_analyzer(self.conn)
        self.distraction = get_distraction_tracker(self.conn)
        self.tracker = get_time_tracker(self.conn)
        self.sessions = get_session_detector(self.conn)
        self.goals = get_goal_service(self.conn)
    
    def make_layout(self) -> Layout:
        """Create the dashboard layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )
        
        layout["left"].split_column(
            Layout(name="stats", ratio=1),
            Layout(name="heatmap", ratio=2)
        )
        
        return layout
    
    def render_header(self) -> Panel:
        """Render header with title and status."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="center")
        grid.add_column(justify="right")
        
        grid.add_row(
            "🧠 [bold cyan]KrypticTrack Live",
            "[bold]Productivity Dashboard",
            f"[dim]{datetime.now().strftime('%H:%M:%S')}[/]"
        )
        
        return Panel(grid, style="white on blue")
    
    def render_stats(self) -> Panel:
        """Render key statistics."""
        today = datetime.now()
        start_of_day = today.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = today.replace(hour=23, minute=59, second=59).timestamp()
        
        # Get today's data
        try:
            distraction_data = self.distraction.track_distractions(start_of_day, end_of_day)
            focus_breakdown = self.distraction.get_focus_vs_distracted_breakdown(start_of_day, end_of_day)
            peak_hours = self.analyzer.get_peak_hours(days=7)
            active_goals = self.goals.get_active_goals()
        except:
            distraction_data = {'context_switches': 0, 'total_distraction_minutes': 0}
            focus_breakdown = {'focus_percentage': 0, 'focused_minutes': 0}
            peak_hours = []
            active_goals = []
        
        # Create stats table
        stats = Table.grid(padding=(0, 2))
        stats.add_column(style="bold cyan", justify="right")
        stats.add_column(style="bold green")
        stats.add_column(style="bold cyan", justify="right")
        stats.add_column(style="bold yellow")
        
        stats.add_row(
            "🎯 Focus", f"{focus_breakdown['focus_percentage']:.0f}%",
            "⚠️  Switches", f"{distraction_data['context_switches']}"
        )
        stats.add_row(
            "⏱️  Focused", f"{focus_breakdown.get('focused_formatted', '0m')}",
            "📊 Goals", f"{len(active_goals)}"
        )
        
        if peak_hours:
            peak = peak_hours[0][0]
            peak_score = peak_hours[0][1]
            stats.add_row(
                "🔥 Peak Hour", f"{peak}",
                "📈 Score", f"{peak_score:.0f}"
            )
        
        return Panel(stats, title="[bold]📊 Today's Stats", border_style="cyan", box=box.ROUNDED)
    
    def render_heatmap(self) -> Panel:
        """Render productivity heatmap."""
        from backend.services.heatmap_generator import get_heatmap_generator
        
        try:
            heatmap_gen = get_heatmap_generator(self.conn)
            heatmap_str = heatmap_gen.generate_weekly_heatmap()
            # Take first 10 lines for compact view
            lines = heatmap_str.split('\n')[:10]
            compact_heatmap = '\n'.join(lines)
        except:
            compact_heatmap = "Generating heatmap..."
        
        return Panel(
            compact_heatmap,
            title="[bold]🔥 7-Day Productivity Heatmap",
            border_style="magenta",
            box=box.ROUNDED
        )
    
    def render_sidebar(self) -> Panel:
        """Render right sidebar with goals and recent activity."""
        # Goals section
        try:
            goals = self.goals.get_active_goals()
        except:
            goals = []
        
        content = []
        content.append("[bold yellow]🎯 Active Goals[/]\n")
        
        if goals:
            for i, goal in enumerate(goals[:3], 1):
                content.append(f"  {i}. {goal['goal_text'][:30]}")
        else:
            content.append("  [dim]No active goals[/]")
        
        content.append("\n[bold cyan]📈 Recent Activity[/]\n")
        content.append("  • Just now")
        content.append("  • 2m ago")
        content.append("  • 5m ago")
        
        return Panel(
            "\n".join(content),
            title="[bold]Info",
            border_style="green",
            box=box.ROUNDED
        )
    
    def render_footer(self) -> Panel:
        """Render footer with controls."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="center")
        
        grid.add_row(
            "[bold cyan]q[/] Quit  [bold cyan]r[/] Refresh  [bold cyan]h[/] Heatmap  [bold cyan]d[/] Distractions  [bold cyan]g[/] Goals"
        )
        
        return Panel(grid, style="white on dark_blue")
    
    def run(self):
        """Run the live dashboard."""
        layout = self.make_layout()
        
        with Live(layout, refresh_per_second=1, screen=True):
            while True:
                # Update all panels
                layout["header"].update(self.render_header())
                layout["stats"].update(self.render_stats())
                layout["heatmap"].update(self.render_heatmap())
                layout["right"].update(self.render_sidebar())
                layout["footer"].update(self.render_footer())
                
                time.sleep(1)


if __name__ == "__main__":
    try:
        dashboard = LiveProductivityDashboard()
        dashboard.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
