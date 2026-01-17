#!/usr/bin/env python3
"""
Live TUI to observe actions landing in the KrypticTrack database.

Shows recent inserts, running counts by source/action type, and updates in real time.
"""

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError as exc:
    print("This tool requires the 'rich' package. Install it with `pip install rich`.")
    raise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.helpers import load_config  # noqa: E402

console = Console()


def resolve_db_path(override: Optional[str] = None) -> Path:
    config = load_config()
    db_path = Path(override or config['database']['path'])
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return db_path


def fetch_new_actions(conn: sqlite3.Connection, last_id: int, batch_size: int) -> List[sqlite3.Row]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, timestamp, source, action_type, context_json
        FROM actions
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (last_id, batch_size),
    )
    return cursor.fetchall()


def describe_context(context: Dict[str, Any]) -> str:
    keys = [
        'full_command',
        'command',
        'url',
        'file_path',
        'title',
        'app',
        'package_manager',
        'git_command',
    ]
    for key in keys:
        value = context.get(key)
        if value:
            value = str(value)
            return value if len(value) <= 80 else value[:77] + '…'
    if context:
        snippet = json.dumps(context)
        return snippet if len(snippet) <= 80 else snippet[:77] + '…'
    return '—'


def infer_feed_label(action_type: str, context: Dict[str, Any]) -> str:
    priority = [
        ('shell', lambda v: f"{v} shell"),
        ('browser', lambda v: f"{v} browser"),
        ('package_manager', lambda v: f"{v} packages"),
        ('git_command', lambda v: f"git {v}"),
        ('git_repo', lambda v: Path(v).name if v else v),
        ('app', lambda v: v),
    ]
    for key, formatter in priority:
        value = context.get(key)
        if value:
            try:
                label = formatter(value)
            except Exception:
                label = value
            if label:
                return str(label)
    return action_type


def format_relative(timestamp: float) -> str:
    if not timestamp:
        return '—'
    delta = time.time() - timestamp
    if delta < 1:
        return 'now'
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    days = int(delta // 86400)
    return f"{days}d ago"


def render_layout(state: Dict[str, Any]) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name='header', size=4),
        Layout(name='main', ratio=3),
        Layout(name='footer', size=3),
    )
    layout['main'].split_row(
        Layout(name='table'),
        Layout(name='stats', size=38),
    )

    header_table = Table.grid(expand=True)
    header_table.add_column(justify='left')
    header_table.add_column(justify='right')
    header_table.add_row(
        f"🧠 Total captured this session: [bold]{state['total_seen']}[/bold]",
        f"DB: {state['db_path'].name} (id {state['last_id']})",
    )
    feed_text = state['last_feed'] or '—'
    header_table.add_row(
        f"Last feed: {feed_text}",
        f"Updated: {time.strftime('%H:%M:%S', time.localtime(state['last_refresh']))}",
    )
    layout['header'].update(Panel(header_table, title="KrypticTrack Action Stream", border_style="cyan"))

    table = Table(expand=True, box=None)
    table.add_column("ID", justify="right", style="dim", no_wrap=True)
    table.add_column("Source", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Feed", style="green", no_wrap=True)
    table.add_column("Details", style="white")
    table.add_column("When", justify="right", style="dim", no_wrap=True)

    if state['recent_entries']:
        for entry in reversed(state['recent_entries']):
            table.add_row(
                str(entry['id']),
                entry['source'] or '—',
                entry['action_type'],
                entry['feed'] or '—',
                entry['detail'],
                format_relative(entry['timestamp']),
            )
    else:
        table.add_row('—', '—', '—', '—', 'Waiting for data…', '—')

    layout['table'].update(Panel(table, title="Recent Actions", border_style="white"))

    stats_table = Table.grid(expand=True)
    stats_table.add_column()
    stats_table.add_row("[bold]Top Sources[/bold]")
    if state['source_counts']:
        for name, count in state['source_counts'].most_common(5):
            stats_table.add_row(f"• {name}: [bold]{count}[/bold]")
    else:
        stats_table.add_row("  (no data yet)")

    stats_table.add_row("")
    stats_table.add_row("[bold]Top Action Types[/bold]")
    if state['action_counts']:
        for name, count in state['action_counts'].most_common(5):
            stats_table.add_row(f"• {name}: [bold]{count}[/bold]")
    else:
        stats_table.add_row("  (no data yet)")

    layout['stats'].update(Panel(stats_table, title="Breakdown", border_style="green"))

    footer_text = Text("Ctrl+C to exit • polling every "
                       f"{state['interval']}s • showing last {state['recent_entries'].maxlen} inserts",
                       justify="center", style="dim")
    layout['footer'].update(Panel(footer_text))
    return layout


def main():
    parser = argparse.ArgumentParser(description="Live view of actions flowing into KrypticTrack DB.")
    parser.add_argument('--db', help="Path to SQLite DB (default from config).")
    parser.add_argument('--interval', type=float, default=1.0, help="Polling interval in seconds.")
    parser.add_argument('--batch', type=int, default=100, help="Max actions to read per poll.")
    parser.add_argument('--history', type=int, default=25, help="How many recent actions to display.")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    if not db_path.exists():
        console.print(f"[red]Database not found at {db_path}. Start the backend/logger first.[/red]")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(id) FROM actions")
        last_id_row = cursor.fetchone()
        last_id = last_id_row[0] or 0
    except sqlite3.Error as exc:
        console.print(f"[red]Could not read actions table: {exc}[/red]")
        sys.exit(1)

    recent_entries: Deque[Dict[str, Any]] = deque(maxlen=args.history)
    source_counts: Counter = Counter()
    action_counts: Counter = Counter()
    total_seen = 0
    last_feed = None

    state = {
        'db_path': db_path,
        'total_seen': total_seen,
        'last_id': last_id,
        'last_feed': last_feed,
        'recent_entries': recent_entries,
        'source_counts': source_counts,
        'action_counts': action_counts,
        'interval': args.interval,
        'last_refresh': time.time(),
    }

    console.print(f"[cyan]Watching {db_path} starting after id {last_id}. Press Ctrl+C to stop.[/cyan]")

    try:
        with Live(render_layout(state), console=console, refresh_per_second=4) as live:
            while True:
                new_rows = fetch_new_actions(conn, last_id, args.batch)
                if new_rows:
                    for row in new_rows:
                        last_id = row['id']
                        timestamp = row['timestamp']
                        context = {}
                        if row['context_json']:
                            try:
                                context = json.loads(row['context_json'])
                            except Exception:
                                context = {}
                        detail = describe_context(context)
                        feed = infer_feed_label(row['action_type'], context)
                        recent_entries.append({
                            'id': row['id'],
                            'source': row['source'],
                            'action_type': row['action_type'],
                            'detail': detail,
                            'feed': feed,
                            'timestamp': timestamp,
                        })
                        source_counts[row['source'] or 'unknown'] += 1
                        action_counts[row['action_type']] += 1
                        total_seen += 1
                        last_feed = feed

                    state['total_seen'] = total_seen
                    state['last_id'] = last_id
                    state['last_feed'] = last_feed

                state['last_refresh'] = time.time()
                live.update(render_layout(state))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        console.print("\n[green]Stopped action monitor.[/green]")
    finally:
        conn.close()


if __name__ == '__main__':
    main()


