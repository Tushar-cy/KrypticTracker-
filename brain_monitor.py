#!/usr/bin/env python3
"""
🧠 Brain Monitor - Live Productivity Dashboard  
Real-time gtop-style monitoring
"""

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import BarColumn, Progress, TextColumn
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
from backend.services.goal_service import get_goal_service


def make_header(refresh_count: int) -> Panel:
    """Create header."""
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=1)
    
    grid.add_row(
        f"[dim]#{refresh_count}[/]",
        "[bold white on blue] 🧠 BRAIN MONITOR - Real-time Productivity Dashboard [/]",
        f"[bold cyan]{datetime.now().strftime('%H:%M:%S')}[/]"
    )
    
    return Panel(grid, style="white on blue", box=box.HEAVY, padding=0)


def make_stats(data: dict) -> Panel:
    """Create stats grid."""
    focus_pct = data['focus']['focus_percentage']
    switches = data['distractions']['context_switches']
    focused_time = data['focus']['focused_formatted']
    goals_count = len(data['goals'])
    
    if data['peak_hours']:
        peak_hour = data['peak_hours'][0][0]
        peak_score = f"{data['peak_hours'][0][1]:.0f}"
    else:
        peak_hour, peak_score = "N/A", "0"
    
    distracted = data['distractions']['total_distraction_minutes']
    
    # Create compact stats table
    table = Table.grid(padding=1, expand=True)
    for _ in range(8):
        table.add_column(justify="center")
    
    # Row 1
    table.add_row(
        "[bold cyan]🎯 FOCUS[/]",
        f"[bold green]{focus_pct:.0f}%[/]",
        "[bold cyan]⚠️ SWITCHES[/]",
        f"[bold yellow]{switches}[/]",
        "[bold cyan]⏱️ FOCUSED[/]",
        f"[bold green]{focused_time}[/]",
        "[bold cyan]📊 GOALS[/]",
        f"[bold magenta]{goals_count}[/]"
    )
    
    # Row 2  
    table.add_row(
        "[bold cyan]🔥 PEAK[/]",
        f"[bold yellow]{peak_hour}[/]",
        "[bold cyan]📈 SCORE[/]",
        f"[bold yellow]{peak_score}[/]",
        "[bold cyan]😴 DISTRACTED[/]",
        f"[bold red]{distracted:.0f}m[/]",
        "[bold cyan]💸 COST[/]",
        f"[bold red]{distracted*23:.0f}m[/]"
    )
    
    return Panel(table, title="[bold]📊 Stats", border_style="cyan", box=box.ROUNDED)


def make_progress(data: dict) -> Panel:
    """Create progress bars."""
    progress = Progress(
        TextColumn("[bold]{task.description}", justify="left"),
        BarColumn(bar_width=40),
        TextColumn("[cyan]{task.percentage:>3.0f}%"),
        expand=True
    )
    
    focus_pct = data['focus']['focus_percentage']
    progress.add_task("🎯 Focus Time", completed=focus_pct, total=100)
    
    goal_pct = min(len(data['goals']) * 33, 100)
    progress.add_task("📊 Goals Active", completed=goal_pct, total=100)
    
    peak_pct = data['peak_hours'][0][1] if data['peak_hours'] else 0
    progress.add_task("🔥 Peak Performance", completed=peak_pct, total=100)
    
    return Panel(progress, title="[bold]📈 Metrics", border_style="green", box=box.ROUNDED)


def make_heatmap(data: dict) -> Panel:
    """Create mini heatmap."""
    hourly = data['hourly']
    current_hour = datetime.now().hour
    
    lines = []
    for hour in range(max(0, current_hour - 4), min(24, current_hour + 2)):
        score = hourly.get(hour, 0)
        bar_len = int(score / 100 * 25)
        
        if score >= 75:
            bar, icon = "[green]" + "█" * bar_len + "[/]", "🔥"
        elif score >= 50:
            bar, icon = "[yellow]" + "█" * bar_len + "[/]", "💪"
        elif score >= 25:
            bar, icon = "[cyan]" + "▓" * bar_len + "[/]", "📊"
        else:
            bar, icon = "[dim]" + "░" * max(1, bar_len) + "[/]", "💤"
        
        marker = "[bold cyan]→[/] " if hour == current_hour else "  "
        lines.append(f"{marker}{hour:02d}:00 {icon} {bar:<30} [dim]{score:>5.1f}[/]")
    
    return Panel("\n".join(lines), title="[bold]🔥 Today's Activity", border_style="magenta", box=box.ROUNDED)


def make_sidebar(data: dict) -> Layout:
    """Create sidebar with goals and distractions."""
    layout = Layout()
    layout.split_column(
        Layout(make_goals(data), name="goals"),
        Layout(make_distractions(data), name="dist")
    )
    return layout


def make_goals(data: dict) -> Panel:
    """Goals panel."""
    goals = data['goals']
    if not goals:
        content = "[dim]No active goals.\nUse TUI to add![/]"
    else:
        lines = [f"{'✅' if i%2==0 else '🎯'} {g['goal_text'][:35]}" for i, g in enumerate(goals[:4], 1)]
        content = "\n".join(lines)
    
    return Panel(content, title=f"[bold]🎯 Goals ({len(goals)})", border_style="green", box=box.ROUNDED)


def make_distractions(data: dict) -> Panel:
    """Distractions panel."""
    categories = data['distractions']['by_category']
    
    if not categories:
        content = "[green]✨ No distractions!\nGreat focus![/]"
    else:
        emoji_map = {'social_media': '📱', 'messaging': '💬', 'entertainment': '🎮', 'browsing': '🌐'}
        lines = []
        for cat, mins in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:4]:
            emoji = emoji_map.get(cat, '•')
            lines.append(f"{emoji} {cat.replace('_',' ').title()}: [red]{int(mins)}m[/]")
        content = "\n".join(lines)
    
    return Panel(content, title="[bold]⚠️ Distractions", border_style="red", box=box.ROUNDED)


def make_footer() -> Panel:
    """Footer."""
    return Panel(
        "[dim]Press [bold]Ctrl+C[/bold] to exit  •  Updates every second  •  Data cached 5s[/]",
        style="white on dark_blue"
    )


def fetch_data(conn) -> dict:
    """Fetch all data."""
    today = datetime.now()
    start = today.replace(hour=0, minute=0, second=0).timestamp()
    end = today.replace(hour=23, minute=59, second=59).timestamp()
    
    try:
        analyzer = get_productivity_pattern_analyzer(conn)
        distraction = get_distraction_tracker(conn)
        goals_service = get_goal_service(conn)
        
        return {
            'distractions': distraction.track_distractions(start, end),
            'focus': distraction.get_focus_vs_distracted_breakdown(start, end),
            'peak_hours': analyzer.get_peak_hours(days=7),
            'goals': goals_service.get_active_goals(),
            'hourly': analyzer.analyze_hourly_productivity(start, end),
        }
    except:
        return {
            'distractions': {'context_switches': 0, 'total_distraction_minutes': 0, 'by_category': {}},
            'focus': {'focus_percentage': 0, 'focused_minutes': 0, 'focused_formatted': '0m'},
            'peak_hours': [],
            'goals': [],
            'hourly': {},
        }


def main():
    """Main loop."""
    console = Console()
    console.clear()
    console.print("[bold cyan]🧠 Starting Brain Monitor...[/]\n")
    
    db = DatabaseManager('data/kryptic_track.db', False)
    conn = db.connect()
    create_tables(conn)
    
    refresh_count = 0
    last_fetch = 0
    cached_data = None
    
    def create_layout() -> Layout:
        """Create complete layout."""
        nonlocal refresh_count, last_fetch, cached_data
        
        # Fetch data (cached for 5s)
        if time.time() - last_fetch > 5:
            cached_data = fetch_data(conn)
            last_fetch = time.time()
        
        refresh_count += 1
        
        # Build layout
        layout = Layout()
        layout.split_column(
            Layout(make_header(refresh_count), name="header", size=3),
            Layout(make_stats(cached_data), name="stats", size=6),
            Layout(name="body"),
            Layout(make_footer(), name="footer", size=3)
        )
        
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(make_sidebar(cached_data), name="right", ratio=1)
        )
        
        layout["left"].split_column(
            Layout(make_progress(cached_data), name="progress", size=7),
            Layout(make_heatmap(cached_data), name="heatmap")
        )
        
        return layout
    
    try:
        with Live(create_layout(), refresh_per_second=1, screen=True, console=console):
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        console.clear()
        console.print("\n[bold cyan]👋 Brain Monitor stopped![/]\n")
        db.close()


if __name__ == "__main__":
    main()
