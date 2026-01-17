"""
KrypticTrack - Enhanced TUI Dashboard (Inspired by train_irl.py)

A beautiful, live-updating terminal interface with:
- Split-panel layouts
- ASCII sparklines
- Real-time metrics with deltas
- Recent activity feeds
- Data source breakdowns
"""

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich import box
from datetime import datetime, timedelta
import time
import sys
from pathlib import Path
from collections import defaultdict, deque

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.daily_summary import get_daily_summary_generator
from backend.services.session_detector import get_session_detector
from backend.services.time_tracker import get_time_tracker
from backend.services.goal_service import get_goal_service
from backend.services.llm_service import get_llm_service


class EnhancedKrypticTrackTUI:
    """Enhanced TUI with live updates and sparklines."""
    
    def __init__(self):
        """Initialize enhanced TUI."""
        self.console = Console()
        self.db = DatabaseManager(db_path='data/kryptic_track.db', encrypted=False)
        self.conn = self.db.connect()
        create_tables(self.conn)
        
        # Initialize services
        self.summary_gen = get_daily_summary_generator(self.conn)
        self.session_detector = get_session_detector(self.conn)
        self.time_tracker = get_time_tracker(self.conn)
        self.goal_service = get_goal_service(self.conn)
        self.llm = get_llm_service()
        
        # State
        self.current_view = "home"
        self.selected_date = datetime.now().strftime('%Y-%m-%d')
        self.running = True
        
        # Metrics history for sparklines
        self.focus_score_history = deque(maxlen=20)
        self.actions_per_day_history = deque(maxlen=20)
        self.time_spent_history = deque(maxlen=20)
        
        # Recent activity
        self.recent_actions = deque(maxlen=10)
        self.last_update = time.time()
    
    def _make_sparkline(self, data: list, width: int = 20) -> str:
        """Create ASCII sparkline from data."""
        if not data or len(data) < 2:
            return "▁" * width
        
        data_min = min(data)
        data_max = max(data)
        data_range = data_max - data_min if data_max > data_min else 1
        
        # Limit to width
        if len(data) > width:
            data = data[-width:]
        
        # Unicode block characters for sparkline
        chars = "▁▂▃▄▅▆▇█"
        result = ""
        
        for value in data:
            normalized = (value - data_min) / data_range
            char_idx = min(int(normalized * (len(chars) - 1)), len(chars) - 1)
            result += chars[char_idx]
        
        # Pad if needed
        while len(result) < width:
            result += "▁"
        
        return result
    
    def _make_progress_bar(self, current: float, total: float, width: int = 30) -> str:
        """Create Unicode progress bar."""
        if total == 0:
            return "░" * width
        
        percentage = min((current / total) * 100, 100)
        filled = int((percentage / 100) * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {percentage:.0f}%"
    
    def _format_delta(self, current: float, previous: float, is_higher_better: bool = True) -> str:
        """Format delta with color and arrow."""
        if previous == 0:
            return ""
        
        delta = current - previous
        if abs(delta) < 0.01:
            return "[dim]~[/dim]"
        
        arrow = "↑" if delta > 0 else "↓"
        color = "green" if (delta > 0) == is_higher_better else "red"
        
        return f"[{color}]{arrow} {abs(delta):.1f}[/{color}]"
    
    def _time_ago(self, timestamp: float) -> str:
        """Format timestamp as 'X ago'."""
        seconds = time.time() - timestamp
        if seconds < 60:
            return f"{int(seconds)}s ago"
        elif seconds < 3600:
            return f"{int(seconds/60)}m ago"
        elif seconds < 86400:
            return f"{int(seconds/3600)}h ago"
        else:
            return f"{int(seconds/86400)}d ago"
    
    def render_home(self) -> Layout:
        """Render home view with live layout."""
        layout = Layout()
        
        # Split into header, body, footer
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        # Split body into left (main) and right (stats)
        layout["body"].split_row(
            Layout(name="main", ratio=3),
            Layout(name="stats", ratio=2)
        )
        
        # Split main into metrics and activity
        layout["main"].split_column(
            Layout(name="metrics", size=14),
            Layout(name="activity", ratio=1)
        )
        
        # Header
        status = "🟢 LLM Online" if self.llm.is_available() else "🔴 LLM Offline"
        header_text = Text()
        header_text.append("🧠 ", style="bold cyan")
        header_text.append("KrypticTrack", style="bold white")
        header_text.append(" - Your Laptop Brain", style="dim")
        
        header = Panel(
            header_text,
            subtitle=f"{datetime.now().strftime('%B %d, %Y - %H:%M:%S')} | {status}",
            border_style="cyan",
            box=box.DOUBLE
        )
        layout["header"].update(header)
        
        # Metrics panel - Today's overview
        metrics_table = self._create_metrics_table()
        metrics_panel = Panel(
            metrics_table,
            title="[bold cyan]📊 Today's Overview",
            border_style="blue",
            box=box.ROUNDED
        )
        layout["metrics"].update(metrics_panel)
        
        # Activity feed
        activity_table = self._create_activity_feed()
        activity_panel = Panel(
            activity_table,
            title="[bold yellow]📝 Recent Activity",
            border_style="yellow",
            box=box.ROUNDED
        )
        layout["activity"].update(activity_panel)
        
        # Stats panel
        stats_table = self._create_stats_panel()
        stats_panel = Panel(
            stats_table,
            title="[bold green]📈 Statistics & Trends",
            border_style="green",
            box=box.ROUNDED
        )
        layout["stats"].update(stats_panel)
        
        # Footer
        footer_table = Table(show_header=False, box=None, padding=(0, 2))
        footer_table.add_column(style="dim", justify="center")
        footer_table.add_row("[1] Summary  [2] Goals  [3] Sessions  [4] Chat  [5] Stats  [q] Quit")
        
        footer = Panel(footer_table, box=box.ROUNDED, border_style="dim")
        layout["footer"].update(footer)
        
        return layout
    
    def _create_metrics_table(self) -> Table:
        """Create metrics table with sparklines."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold white", width=20)
        table.add_column(style="cyan", justify="right")
        
        # Get today's data
        today = datetime.now().strftime('%Y-%m-%d')
        dt = datetime.strptime(today, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        # Get counts
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
        """, (start_of_day, end_of_day))
        today_actions = cursor.fetchone()[0]
        
        # Get sessions
        sessions = self.session_detector.detect_sessions(start_of_day, end_of_day)
        session_count = len(sessions)
        
        # Get time breakdown
        try:
            time_breakdown = self.time_tracker.get_daily_breakdown(today)
            total_time = time_breakdown.get('total_time', {}).get('minutes', 0)
            productivity = time_breakdown.get('productivity', {})
            focus_score = productivity.get('focus_score', 0)
            context_switches = productivity.get('context_switches', 0)
        except Exception as e:
            # Fallback if time_tracker fails
            total_time = 0
            focus_score = 0
            context_switches = 0
        
        # Update histories
        self.focus_score_history.append(focus_score)
        self.actions_per_day_history.append(today_actions)
        self.time_spent_history.append(total_time)
        
        # Display with sparklines
        table.add_row("⏱️  Active Time", f"{total_time:.0f}m")
        if len(self.time_spent_history) > 1:
            sparkline = self._make_sparkline(list(self.time_spent_history), 15)
            table.add_row("   7-day trend", f"[cyan]{sparkline}[/cyan]")
        
        table.add_row("", "")  # Spacer
        
        # Focus score with delta
        prev_focus = self.focus_score_history [-2] if len(self.focus_score_history) > 1 else focus_score
        delta = self._format_delta(focus_score, prev_focus, is_higher_better=True)
        table.add_row("🎯 Focus Score", f"{focus_score:.0f}/100 {delta}")
        if len(self.focus_score_history) > 1:
            sparkline = self._make_sparkline(list(self.focus_score_history), 15)
            table.add_row("   Score trend", f"[green]{sparkline}[/green]")
        
        table.add_row("", "")  # Spacer
        
        table.add_row("📊 Sessions", str(session_count))
        table.add_row("📝 Actions", f"{today_actions:,}")
        table.add_row("🔄 Switches", str(context_switches))
        
        return table
    
    def _create_activity_feed(self) -> Table:
        """Create recent activity feed."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="dim", width=12)
        table.add_column(style="white")
        
        # Get recent actions
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT timestamp, source, action_type, context_json
            FROM actions
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        
        import json
        for row in cursor.fetchall():
            timestamp = row[0]
            source = row[1]
            action_type = row[2]
            
            time_str = self._time_ago(timestamp)
            
            # Get emoji for source
            source_emoji = {
                'system': '🖥️',
                'vscode': '💻',
                'chrome': '🌐',
                'zsh': '🐚',
                'git': '📦'
            }.get(source.lower(), '•')
            
            action_display = action_type.replace('_', ' ').title()[:30]
            table.add_row(time_str, f"{source_emoji} {source}: {action_display}")
        
        if table.row_count == 0:
            table.add_row("", "[dim]No recent activity[/dim]")
        
        return table
    
    def _create_stats_panel(self) -> Table:
        """Create stats panel with system info."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold white")
        table.add_column(style="cyan", justify="right")
        
        cursor = self.conn.cursor()
        
        # Total actions
        cursor.execute("SELECT COUNT(*) FROM actions")
        total_actions = cursor.fetchone()[0]
        table.add_row("📊 Total Actions", f"{total_actions:,}")
        
        # Active goals
        cursor.execute("SELECT COUNT(*) FROM user_goals WHERE status='active'")
        active_goals = cursor.fetchone()[0]
        table.add_row("🎯 Active Goals", str(active_goals))
        
        table.add_row("", "")  # Spacer
        
        # Data sources breakdown
        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM actions
            GROUP BY source
            ORDER BY count DESC
            LIMIT 5
        """)
        
        table.add_row(Text("Data Sources:", style="bold yellow"), "")
        for row in cursor.fetchall():
            source, count = row
            emoji = {
                'system': '🖥️  System',
                'vscode': '💻 VS Code',
                'chrome': '🌐 Chrome',
                'zsh': '🐚 Zsh'
            }.get(source.lower(), source)
            table.add_row(f"  {emoji}", f"{count:,}")
        
        table.add_row("", "")  # Spacer
        
        # Action types
        cursor.execute("""
            SELECT action_type, COUNT(*) as count
            FROM actions
            GROUP BY action_type
            ORDER BY count DESC
            LIMIT 5
        """)
        
        table.add_row(Text("Top Actions:", style="bold magenta"), "")
        for row in cursor.fetchall():
            action_type, count = row
            display = action_type.replace('_', ' ').title()[:18]
            table.add_row(f"  • {display}", f"{count:,}")
        
        return table
    
    def run_live(self):
        """Run with live updates."""
        try:
            with Live(self.render_home(), refresh_per_second=1, console=self.console) as live:
                while self.running:
                    # Update every second
                    time.sleep(1)
                    live.update(self.render_home())
                    
                    # Check for user input (non-blocking)
                    # Note: In a real implementation, you'd use threading or async
                    # for input handling. For simplicity, we'll break after timeout
                    
                    # Auto-exit after showing for a bit (for demo)
                    if time.time() - self.last_update > 10:
                        break
        
        except KeyboardInterrupt:
            pass
        
        self.console.print("\n[cyan]Exiting live mode. Switching to interactive mode...[/cyan]\n")
        time.sleep(1)
    
    def run_interactive(self):
        """Run normal interactive mode."""
        while self.running:
            self.console.clear()
            self.console.print(self.render_home())
            
            choice = Prompt.ask("\n[bold cyan]Select[/]", default="1")
            
            if choice == "1":
                self.view_daily_summary()
            elif choice == "2":
                self.view_goals()
            elif choice == "3":
                self.view_sessions()
            elif choice == "4":
                self.chat_with_llm()
            elif choice == "5":
                self.show_quick_stats()
            elif choice.lower() in ['q', 'quit', 'exit']:
                if Confirm.ask("\n[yellow]Are you sure you want to quit?[/]"):
                    self.running = False
        
        self.console.print("\n[cyan]👋 Thank you for using KrypticTrack![/]\n")
        self.db.close()
    
    # Keep existing methods from original TUI
    def view_daily_summary(self):
        """Show daily summary (from original TUI)."""
        from tui_dashboard import KrypticTrackTUI
        tui = KrypticTrackTUI()
        tui.view_daily_summary()
    
    def view_goals(self):
        from tui_dashboard import KrypticTrackTUI
        tui = KrypticTrackTUI()
        tui.view_goals()
    
    def view_sessions(self):
        from tui_dashboard import KrypticTrackTUI
        tui = KrypticTrackTUI()
        tui.view_sessions()
    
    def chat_with_llm(self):
        from tui_dashboard import KrypticTrackTUI
        tui = KrypticTrackTUI()
        tui.chat_with_llm()
    
    def show_quick_stats(self):
        from tui_dashboard import KrypticTrackTUI
        tui = KrypticTrackTUI()
        tui.show_quick_stats()


def main():
    """Entry point."""
    app = EnhancedKrypticTrackTUI()
    
    # Show live view for a few seconds
    app.console.print("[bold cyan]🧠 Starting KrypticTrack Enhanced TUI...[/]")
    app.console.print("[dim]Live dashboard mode for 10 seconds, then interactive...[/]\n")
    time.sleep(2)
    
    # Run live mode
    app.run_live()
    
    # Then switch to interactive
    app.run_interactive()


if __name__ == "__main__":
    main()
