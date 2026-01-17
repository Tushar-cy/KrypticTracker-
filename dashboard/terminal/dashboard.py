#!/usr/bin/env python3
"""Terminal dashboard for real-time monitoring using Rich."""

import time
import sys
from pathlib import Path
import requests
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.text import Text

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.helpers import load_config

API_URL = "http://localhost:5000/api"
API_KEY = "local-dev-key-change-in-production"

console = Console()


def get_stats():
    """Fetch stats from API."""
    try:
        response = requests.get(
            f"{API_URL}/stats",
            headers={"X-API-Key": API_KEY},
            timeout=1
        )
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def get_recent_actions(limit=10):
    """Fetch recent actions."""
    try:
        response = requests.get(
            f"{API_URL}/recent-actions",
            params={"limit": limit},
            headers={"X-API-Key": API_KEY},
            timeout=1
        )
        if response.status_code == 200:
            return response.json().get("actions", [])
    except:
        pass
    return []


def format_timestamp(ts):
    """Format timestamp to readable time."""
    return time.strftime("%H:%M:%S", time.localtime(ts))


def format_duration(seconds):
    """Format duration."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def create_layout():
    """Create dashboard layout."""
    layout = Layout()
    
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3)
    )
    
    layout["main"].split_row(
        Layout(name="left"),
        Layout(name="right")
    )
    
    layout["left"].split_column(
        Layout(name="stats"),
        Layout(name="predictions")
    )
    
    layout["right"].split_column(
        Layout(name="actions", ratio=2),
        Layout(name="insights", ratio=1)
    )
    
    return layout


def create_header():
    """Create header panel."""
    return Panel(
        Text("🧠 IRL BEHAVIOR TRACKER - LIVE MONITORING", style="bold cyan", justify="center"),
        border_style="cyan"
    )


def create_stats_panel(stats):
    """Create stats panel."""
    if not stats:
        return Panel("Backend not available", title="📊 SESSION STATS", border_style="red")
    
    content = f"""
├─ Actions logged: {stats.get('total_actions', 0):,}
├─ Session time: {format_duration(stats.get('session_duration_seconds', 0))}
└─ Current state: active
"""
    
    return Panel(content, title="📊 SESSION STATS", border_style="green")


def create_predictions_panel():
    """Create predictions panel."""
    content = """
Next action: (Model not trained yet)
Confidence: [Phase 3]
Reason: Training required
"""
    return Panel(content, title="🎯 CURRENT PREDICTION", border_style="yellow")


def create_actions_panel(actions):
    """Create recent actions panel."""
    if not actions:
        return Panel("No actions yet", title="⚡ RECENT ACTIONS", border_style="blue")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Time", style="cyan", width=10)
    table.add_column("Source", style="magenta", width=8)
    table.add_column("Action", style="white")
    
    for action in actions[:10]:
        time_str = format_timestamp(action['timestamp'])
        source = action['source']
        action_type = action['action_type']
        table.add_row(time_str, source, action_type)
    
    return Panel(table, title="⚡ RECENT ACTIONS", border_style="blue")


def create_insights_panel():
    """Create insights panel."""
    content = """
└─ Insights will appear here
   after model training (Phase 4)
"""
    return Panel(content, title="🔥 TODAY'S INSIGHTS", border_style="magenta")


def create_footer():
    """Create footer with controls."""
    return Panel(
        Text("[Q] Quit  [P] Pause  [T] Train  [I] Insights  [S] Stats", justify="center"),
        border_style="dim"
    )


def main():
    """Main dashboard loop."""
    console.clear()
    console.print("[bold cyan]Starting KrypticTrack Terminal Dashboard...[/bold cyan]")
    
    layout = create_layout()
    
    try:
        with Live(layout, refresh_per_second=2, screen=True) as live:
            while True:
                stats = get_stats()
                actions = get_recent_actions(10)
                
                layout["header"].update(create_header())
                layout["stats"].update(create_stats_panel(stats))
                layout["predictions"].update(create_predictions_panel())
                layout["actions"].update(create_actions_panel(actions))
                layout["insights"].update(create_insights_panel())
                layout["footer"].update(create_footer())
                
                time.sleep(0.5)
                
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Dashboard stopped[/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")


if __name__ == "__main__":
    main()




