"""
Training script for IRL model with beautiful TUI (Terminal User Interface).
Loads data from database, extracts features, and trains reward model.
"""

import sys
from pathlib import Path
import sqlite3
import json
import numpy as np
import time
import re
import subprocess
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from threading import Thread, Event
import hashlib
import ast

# Try to import rich for TUI, fallback to basic print if not available
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
    # Sparkline might not be available in all rich versions
    try:
        from rich.sparkline import Sparkline
        HAS_SPARKLINE = True
    except ImportError:
        HAS_SPARKLINE = False
    # Columns might not be available in all rich versions
    try:
        from rich.columns import Columns
        HAS_COLUMNS = True
    except ImportError:
        HAS_COLUMNS = False
    HAS_RICH = True
except ImportError as e:
    HAS_RICH = False
    HAS_SPARKLINE = False
    HAS_COLUMNS = False
    print(f"⚠️  Rich not available: {e}")
    print("   Install with: pip install rich")
    print("   Continuing with basic output...\n")

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from encoding.feature_extractor import FeatureExtractor
from models.irl_algorithm import MaxEntIRL
from database import DatabaseManager
from utils.helpers import load_config


class TrainingTUI:
    """Beautiful terminal UI for training, inspired by htop/gotop."""
    
    def __init__(self):
        self.console = Console() if HAS_RICH else None
        self.current_epoch = 0
        self.total_epochs = 0
        self.current_loss = None
        self.current_reward_mean = None
        self.current_reward_std = None
        self.training_start_time = None
        self.data_loading_progress = 0
        self.data_loading_total = 0
        self.data_loading_status = "Initializing..."
        self.training_status = "Waiting..."
        self.history_loss = []
        self.history_reward_mean = []
        self.history_reward_std = []
        self.stop_event = Event()
        # Recent data tracking
        self.recent_actions = []  # List of recent actions added
        self.data_sources = {}  # Count by source
        self.data_action_types = {}  # Count by action type
        self.last_data_timestamp = None
        self.total_actions_in_db = 0
        # Completion summary
        self.completed = False
        self.completion_summary = {}
        self.new_data_summary = {}
        # Performance metrics
        self.epoch_times = []  # Track time per epoch for ETA
        self.last_epoch_time = None
        self.actions_per_second = 0
        self.estimated_time_remaining = 0
    
    def update_data_loading(self, current: int, total: int, status: str):
        """Update data loading progress."""
        self.data_loading_progress = current
        self.data_loading_total = total
        self.data_loading_status = status
    
    def add_recent_action(self, action_type: str, source: str, context: str = ""):
        """Add a recent action to the display."""
        self.recent_actions.append({
            'type': action_type,
            'source': source,
            'context': context[:50] if context else "",
            'time': time.time()
        })
        # Keep only last 10
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]
        
        # Update counts
        self.data_sources[source] = self.data_sources.get(source, 0) + 1
        self.data_action_types[action_type] = self.data_action_types.get(action_type, 0) + 1
        self.last_data_timestamp = time.time()
    
    def set_total_actions(self, total: int):
        """Set total actions in database."""
        self.total_actions_in_db = total
    
    def update_training(self, epoch: int, total_epochs: int, loss: float = None, 
                       reward_mean: float = None, reward_std: float = None):
        """Update training metrics."""
        current_time = time.time()
        
        # Track epoch timing for ETA
        if epoch > self.current_epoch and self.training_start_time:
            if self.last_epoch_time is None:
                # First epoch - initialize
                self.last_epoch_time = current_time
            else:
                epoch_duration = current_time - self.last_epoch_time
                self.epoch_times.append(epoch_duration)
                # Keep only last 10 epochs for average
                if len(self.epoch_times) > 10:
                    self.epoch_times = self.epoch_times[-10:]
                
                # Calculate ETA
                if len(self.epoch_times) > 0:
                    avg_epoch_time = sum(self.epoch_times) / len(self.epoch_times)
                    remaining_epochs = total_epochs - epoch
                    self.estimated_time_remaining = avg_epoch_time * remaining_epochs
            
            self.last_epoch_time = current_time
        
        self.current_epoch = epoch
        self.total_epochs = total_epochs
        if loss is not None:
            self.current_loss = loss
            self.history_loss.append(loss)
            # Keep only last 50 points for sparkline
            if len(self.history_loss) > 50:
                self.history_loss = self.history_loss[-50:]
        if reward_mean is not None:
            self.current_reward_mean = reward_mean
            self.history_reward_mean.append(reward_mean)
            if len(self.history_reward_mean) > 50:
                self.history_reward_mean = self.history_reward_mean[-50:]
        if reward_std is not None:
            self.current_reward_std = reward_std
            self.history_reward_std.append(reward_std)
            if len(self.history_reward_std) > 50:
                self.history_reward_std = self.history_reward_std[-50:]
    
    def render(self) -> str:
        """Render the TUI layout."""
        if not HAS_RICH:
            return self._render_basic()
        
        # Create layout - improved with more sections
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        layout["body"].split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2)
        )
        layout["left"].split_column(
            Layout(name="metrics", size=12),
            Layout(name="charts", size=8)
        )
        
        # Header
        header = Panel(
            Text("🧠 KrypticTrack IRL Training", style="bold cyan"),
            box=box.ROUNDED,
            border_style="cyan"
        )
        layout["header"].update(header)
        
        # Metrics panel - Training progress
        metrics_table = Table(show_header=False, box=None, padding=(0, 1))
        
        if self.completed:
            # Show completion summary
            metrics_table.add_row(Text("✅ COMPLETE!", style="bold green"), "")
            metrics_table.add_row("", "")
            if self.completion_summary:
                metrics_table.add_row(Text("Model Path:", style="bold"), self.completion_summary.get('model_path', 'N/A')[:50])
                metrics_table.add_row("", "")
                metrics_table.add_row(Text("Final Metrics:", style="bold cyan"), "")
                loss = self.completion_summary.get('final_loss')
                if loss is not None:
                    loss_color = "green" if loss < 0.1 else "yellow" if loss < 0.5 else "red"
                    metrics_table.add_row("  Loss:", Text(f"{loss:.6f}", style=loss_color))
                if self.completion_summary.get('final_reward_mean') is not None:
                    metrics_table.add_row("  Reward μ:", f"{self.completion_summary['final_reward_mean']:.4f}")
                if self.completion_summary.get('final_reward_std') is not None:
                    metrics_table.add_row("  Reward σ:", f"{self.completion_summary['final_reward_std']:.4f}")
                metrics_table.add_row("", "")
                metrics_table.add_row(Text("Training Info:", style="bold cyan"), "")
                metrics_table.add_row("  Epochs:", str(self.completion_summary.get('num_epochs', 'N/A')))
                metrics_table.add_row("  Actions:", f"{self.completion_summary.get('total_actions', 0):,}")
                metrics_table.add_row("  Data Range:", self.completion_summary.get('data_range', 'N/A'))
        else:
            # Normal training progress with enhanced metrics
            metrics_table.add_row(Text("Status:", style="bold"), Text(self.training_status, style="bold green"))
            metrics_table.add_row(Text("Epoch:", style="bold"), f"[cyan]{self.current_epoch}[/cyan]/[dim]{self.total_epochs}[/dim]")
            
            if self.current_loss is not None:
                loss_color = "green" if self.current_loss < 0.1 else "yellow" if self.current_loss < 0.5 else "red"
                # Show loss change if available
                loss_change = ""
                if len(self.history_loss) > 1:
                    change = self.history_loss[-1] - self.history_loss[-2]
                    change_str = f"{change:+.6f}" if abs(change) > 0.000001 else "±0.000000"
                    change_color = "green" if change < 0 else "red" if change > 0 else "dim"
                    loss_change = f" [{change_color}]{change_str}[/{change_color}]"
                metrics_table.add_row(Text("Loss:", style="bold"), Text(f"{self.current_loss:.6f}", style=loss_color) + loss_change)
            
            if self.current_reward_mean is not None:
                reward_change = ""
                if len(self.history_reward_mean) > 1:
                    change = self.history_reward_mean[-1] - self.history_reward_mean[-2]
                    change_str = f"{change:+.4f}" if abs(change) > 0.0001 else "±0.0000"
                    change_color = "green" if change > 0 else "red" if change < 0 else "dim"
                    reward_change = f" [{change_color}]{change_str}[/{change_color}]"
                metrics_table.add_row(Text("Reward μ:", style="bold"), f"{self.current_reward_mean:.4f}" + reward_change)
            
            if self.current_reward_std is not None:
                metrics_table.add_row(Text("Reward σ:", style="bold"), f"{self.current_reward_std:.4f}")
            
            metrics_table.add_row("", "")  # Spacer
            
            # Time metrics
            if self.training_start_time:
                elapsed = time.time() - self.training_start_time
                metrics_table.add_row(Text("Elapsed:", style="bold"), f"[cyan]{elapsed:.1f}s[/cyan]")
                
                # ETA
                if self.estimated_time_remaining > 0:
                    eta_min = int(self.estimated_time_remaining // 60)
                    eta_sec = int(self.estimated_time_remaining % 60)
                    if eta_min > 0:
                        eta_str = f"{eta_min}m {eta_sec}s"
                    else:
                        eta_str = f"{eta_sec}s"
                    metrics_table.add_row(Text("ETA:", style="bold"), f"[yellow]{eta_str}[/yellow]")
                
                # Speed (epochs per second)
                if len(self.epoch_times) > 0:
                    avg_epoch_time = sum(self.epoch_times) / len(self.epoch_times)
                    if avg_epoch_time > 0:
                        epochs_per_sec = 1.0 / avg_epoch_time
                        metrics_table.add_row(Text("Speed:", style="bold"), f"[green]{epochs_per_sec:.2f}[/green] epochs/s")
            
            metrics_table.add_row("", "")  # Spacer
            
            # Progress bar with percentage
            if self.total_epochs > 0:
                progress_pct = min((self.current_epoch / self.total_epochs) * 100, 100.0)
                filled = int(progress_pct / 2)
                progress_bar = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (50 - filled) + "[/dim]"
                metrics_table.add_row(Text("Progress:", style="bold"), f"{progress_bar} [cyan]{progress_pct:.1f}%[/cyan]")
        
        metrics_panel = Panel(metrics_table, title="📊 Training Metrics", border_style="blue", box=box.ROUNDED)
        layout["metrics"].update(metrics_panel)
        
        # Charts panel - Sparklines for loss and reward
        charts_table = Table(show_header=False, box=None, padding=(0, 1))
        
        if not self.completed and len(self.history_loss) > 1:
            # Loss sparkline
            if HAS_SPARKLINE:
                try:
                    loss_spark = Sparkline(self.history_loss[-30:], style="red")
                    loss_text = Text("Loss: ", style="bold red")
                    charts_table.add_row(loss_text, loss_spark)
                except:
                    # Fallback if sparkline fails
                    loss_min = min(self.history_loss)
                    loss_max = max(self.history_loss)
                    loss_range = loss_max - loss_min if loss_max > loss_min else 1
                    loss_chart = "".join(["▁" if (v - loss_min) / loss_range < 0.125 else
                                         "▂" if (v - loss_min) / loss_range < 0.25 else
                                         "▃" if (v - loss_min) / loss_range < 0.375 else
                                         "▄" if (v - loss_min) / loss_range < 0.5 else
                                         "▅" if (v - loss_min) / loss_range < 0.625 else
                                         "▆" if (v - loss_min) / loss_range < 0.75 else
                                         "▇" if (v - loss_min) / loss_range < 0.875 else "█"
                                         for v in self.history_loss[-30:]])
                    charts_table.add_row(Text("Loss: ", style="bold red"), Text(loss_chart, style="red"))
            else:
                # Use ASCII chart fallback
                loss_min = min(self.history_loss)
                loss_max = max(self.history_loss)
                loss_range = loss_max - loss_min if loss_max > loss_min else 1
                loss_chart = "".join(["▁" if (v - loss_min) / loss_range < 0.125 else
                                     "▂" if (v - loss_min) / loss_range < 0.25 else
                                     "▃" if (v - loss_min) / loss_range < 0.375 else
                                     "▄" if (v - loss_min) / loss_range < 0.5 else
                                     "▅" if (v - loss_min) / loss_range < 0.625 else
                                     "▆" if (v - loss_min) / loss_range < 0.75 else
                                     "▇" if (v - loss_min) / loss_range < 0.875 else "█"
                                     for v in self.history_loss[-30:]])
                charts_table.add_row(Text("Loss: ", style="bold red"), Text(loss_chart, style="red"))
        
        if not self.completed and len(self.history_reward_mean) > 1:
            # Reward sparkline
            if HAS_SPARKLINE:
                try:
                    reward_spark = Sparkline(self.history_reward_mean[-30:], style="green")
                    reward_text = Text("Reward: ", style="bold green")
                    charts_table.add_row(reward_text, reward_spark)
                except:
                    # Fallback
                    reward_min = min(self.history_reward_mean)
                    reward_max = max(self.history_reward_mean)
                    reward_range = reward_max - reward_min if reward_max > reward_min else 1
                    reward_chart = "".join(["▁" if (v - reward_min) / reward_range < 0.125 else
                                            "▂" if (v - reward_min) / reward_range < 0.25 else
                                            "▃" if (v - reward_min) / reward_range < 0.375 else
                                            "▄" if (v - reward_min) / reward_range < 0.5 else
                                            "▅" if (v - reward_min) / reward_range < 0.625 else
                                            "▆" if (v - reward_min) / reward_range < 0.75 else
                                            "▇" if (v - reward_min) / reward_range < 0.875 else "█"
                                            for v in self.history_reward_mean[-30:]])
                    charts_table.add_row(Text("Reward: ", style="bold green"), Text(reward_chart, style="green"))
            else:
                # Use ASCII chart fallback
                reward_min = min(self.history_reward_mean)
                reward_max = max(self.history_reward_mean)
                reward_range = reward_max - reward_min if reward_max > reward_min else 1
                reward_chart = "".join(["▁" if (v - reward_min) / reward_range < 0.125 else
                                        "▂" if (v - reward_min) / reward_range < 0.25 else
                                        "▃" if (v - reward_min) / reward_range < 0.375 else
                                        "▄" if (v - reward_min) / reward_range < 0.5 else
                                        "▅" if (v - reward_min) / reward_range < 0.625 else
                                        "▆" if (v - reward_min) / reward_range < 0.75 else
                                        "▇" if (v - reward_min) / reward_range < 0.875 else "█"
                                        for v in self.history_reward_mean[-30:]])
                charts_table.add_row(Text("Reward: ", style="bold green"), Text(reward_chart, style="green"))
        
        if len(charts_table.rows) == 0:
            charts_table.add_row(Text("Charts will appear as training progresses...", style="dim"), "")
        
        charts_panel = Panel(charts_table, title="📈 Trends", border_style="magenta", box=box.ROUNDED)
        layout["charts"].update(charts_panel)
        
        # Right panel - Data details (enhanced)
        right_table = Table(show_header=False, box=None, padding=(0, 1))
        right_table.add_row(Text("Status:", style="bold"), Text(self.data_loading_status, style="bold cyan"))
        
        if self.data_loading_total > 0:
            loading_pct = (self.data_loading_progress / self.data_loading_total) * 100
            filled = int(loading_pct / 2)
            loading_bar = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (50 - filled) + "[/dim]"
            right_table.add_row(Text("Progress:", style="bold"), f"{loading_bar} [cyan]{loading_pct:.1f}%[/cyan]")
            right_table.add_row(Text("Actions:", style="bold"), f"[green]{self.data_loading_progress:,}[/green]/[dim]{self.data_loading_total:,}[/dim]")
            
            # Calculate loading speed
            if self.training_start_time and self.data_loading_progress > 0:
                elapsed = time.time() - self.training_start_time
                if elapsed > 0:
                    actions_per_sec = self.data_loading_progress / elapsed
                    right_table.add_row(Text("Speed:", style="bold"), f"[yellow]{actions_per_sec:.1f}[/yellow] actions/s")
        
        if self.total_actions_in_db > 0:
            right_table.add_row("", "")  # Spacer
            right_table.add_row(Text("Total in DB:", style="bold"), f"{self.total_actions_in_db:,}")
        
        # Data sources breakdown
        if self.data_sources:
            right_table.add_row("", "")  # Spacer
            right_table.add_row(Text("Data Sources:", style="bold cyan"), "")
            for source, count in sorted(self.data_sources.items(), key=lambda x: x[1], reverse=True)[:8]:
                source_display = {
                    'system': '🖥️  System',
                    'vscode': '💻 VS Code',
                    'chrome': '🌐 Chrome',
                    'zsh': '🐚 Zsh',
                    'bash': '🐚 Bash',
                    'git': '📦 Git',
                    'npm': '📦 npm',
                    'pip': '🐍 pip',
                    'python': '🐍 Python REPL'
                }.get(source.lower(), source)
                right_table.add_row(f"  {source_display}:", f"{count:,}")
        
        # Action types breakdown
        if self.data_action_types:
            right_table.add_row("", "")  # Spacer
            right_table.add_row(Text("Action Types:", style="bold cyan"), "")
            for action_type, count in sorted(self.data_action_types.items(), key=lambda x: x[1], reverse=True)[:8]:
                display_name = action_type.replace('_', ' ').title()[:20]
                right_table.add_row(f"  • {display_name}:", f"{count:,}")
        
        # Recent actions
        if self.recent_actions:
            right_table.add_row("", "")  # Spacer
            right_table.add_row(Text("Recent Data:", style="bold yellow"), "")
            for action in self.recent_actions[-5:]:  # Show last 5
                time_ago = time.time() - action['time']
                if time_ago < 60:
                    time_str = f"{int(time_ago)}s ago"
                elif time_ago < 3600:
                    time_str = f"{int(time_ago/60)}m ago"
                else:
                    time_str = f"{int(time_ago/3600)}h ago"
                
                action_display = action['type'].replace('_', ' ').title()[:15]
                source_display = action['source'][:8]
                right_table.add_row(f"  [{time_str}]", f"{source_display}: {action_display}")
        
        # Show new data context if completed
        if self.completed and self.new_data_summary:
            right_table.add_row("", "")  # Spacer
            right_table.add_row(Text("New Context:", style="bold magenta"), "")
            right_table.add_row("  Total Actions:", f"{self.new_data_summary.get('total_actions', 0):,}")
            if self.new_data_summary.get('sources_breakdown'):
                right_table.add_row("  Sources:", "")
                for source, count in list(self.new_data_summary['sources_breakdown'].items())[:3]:
                    right_table.add_row(f"    • {source}:", f"{count:,}")
            if self.new_data_summary.get('action_types'):
                right_table.add_row("  Top Actions:", "")
                for action_type, count in list(self.new_data_summary['action_types'].items())[:3]:
                    display_name = action_type.replace('_', ' ').title()[:18]
                    right_table.add_row(f"    • {display_name}:", f"{count:,}")
        
        right_panel = Panel(right_table, title="📦 Data Details", border_style="green", box=box.ROUNDED)
        layout["right"].update(right_panel)
        
        # Enhanced Footer with more info
        footer_table = Table(show_header=False, box=None, padding=(0, 1))
        footer_table.add_row(Text("Press Ctrl+C to stop training", style="dim"))
        if self.training_start_time and not self.completed:
            elapsed = time.time() - self.training_start_time
            footer_table.add_row(Text(f"Running for {elapsed:.0f}s", style="dim"))
        if self.total_actions_in_db > 0:
            footer_table.add_row(Text(f"Database: {self.total_actions_in_db:,} actions", style="dim"))
        
        footer = Panel(footer_table, box=box.ROUNDED, border_style="dim")
        layout["footer"].update(footer)
        
        return layout
    
    def _render_basic(self) -> str:
        """Basic text output when rich is not available."""
        output = []
        output.append("=" * 60)
        output.append("🧠 KrypticTrack IRL Training")
        output.append("=" * 60)
        output.append(f"Status: {self.training_status}")
        output.append(f"Epoch: {self.current_epoch}/{self.total_epochs}")
        if self.current_loss is not None:
            output.append(f"Loss: {self.current_loss:.6f}")
        if self.current_reward_mean is not None:
            output.append(f"Reward μ: {self.current_reward_mean:.4f}")
        if self.data_loading_total > 0:
            output.append(f"Data: {self.data_loading_progress:,}/{self.data_loading_total:,}")
        return "\n".join(output)


def load_shell_history_to_db(db_path: str, tui: Optional[TrainingTUI] = None) -> int:
    """
    Load shell history (zsh, bash, fish) directly into database.
    Returns number of actions added.
    """
    home = Path.home()
    actions_added = 0
    
    # Get database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if actions table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='actions'")
    if not cursor.fetchone():
        conn.close()
        return 0
    
    # Get last timestamp from database to avoid duplicates
    cursor.execute("SELECT MAX(timestamp) FROM actions WHERE source = 'system'")
    last_timestamp_row = cursor.fetchone()
    last_timestamp = last_timestamp_row[0] if last_timestamp_row[0] else 0
    
    # Load zsh history
    zsh_history = home / '.zsh_history'
    if zsh_history.exists() and tui:
        tui.update_data_loading(0, 1, "Loading zsh history...")
    
    if zsh_history.exists():
        try:
            if tui:
                tui.update_data_loading(0, 1, f"Reading zsh history from {zsh_history}...")
            
            # Read zsh history file - it's binary format with null bytes
            with open(zsh_history, 'rb') as f:
                content = f.read()
            
            # zsh history uses null bytes to separate entries, decode carefully
            # Try to decode as utf-8, handling errors
            try:
                text_content = content.decode('utf-8', errors='replace')
            except:
                # Fallback: replace problematic bytes
                text_content = content.decode('latin-1', errors='replace')
            
            lines = text_content.split('\n')
            total_lines = len(lines)
            
            if tui:
                tui.update_data_loading(0, total_lines, f"Parsing {total_lines} zsh history lines...")
            
            processed = 0
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parse zsh history format: ': timestamp:0;command'
                # Also handle multi-line commands (they may be split)
                match = re.match(r':\s*(\d+):\d+;(.+)', line)
                if match:
                    timestamp = int(match.group(1))
                    command = match.group(2).strip()
                    
                    # Skip very short commands (likely incomplete)
                    if len(command) < 2:
                        continue
                    
                    if command and timestamp > last_timestamp:
                        # Check if already exists (use hash of command for faster lookup)
                        import hashlib
                        cmd_hash = hashlib.md5(command.encode()).hexdigest()
                        cursor.execute("""
                            SELECT COUNT(*) FROM actions 
                            WHERE source = 'system' 
                            AND action_type = 'terminal_command'
                            AND context_json LIKE ?
                        """, (f'%{cmd_hash[:8]}%',))
                        
                        # Also check by command content
                        cursor.execute("""
                            SELECT COUNT(*) FROM actions 
                            WHERE source = 'system' 
                            AND action_type = 'terminal_command'
                            AND context_json LIKE ?
                        """, (f'%"full_command": "{command[:100].replace('"', "")}"%',))
                        
                        if cursor.fetchone()[0] == 0:
                            context = {
                                'command': command.split()[0] if command.split() else '',
                                'full_command': command[:500],
                                'shell': 'zsh',
                                'category': 'other',
                                'cmd_hash': cmd_hash[:8]  # For deduplication
                            }
                            
                            cursor.execute("""
                                INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                                VALUES (?, 'system', 'terminal_command', ?, 'shell_history_import')
                            """, (timestamp, json.dumps(context)))
                            actions_added += 1
                            
                            if tui and actions_added % 100 == 0:
                                tui.update_data_loading(i, total_lines, f"Loaded {actions_added} zsh commands...")
                                tui.add_recent_action('terminal_command', 'zsh', command[:50])
                    
                    processed += 1
                    if processed % 1000 == 0 and tui:
                        tui.update_data_loading(i, total_lines, f"Processed {processed}/{total_lines} lines, added {actions_added} commands...")
            
            if tui:
                tui.update_data_loading(total_lines, total_lines, f"✅ Loaded {actions_added} zsh commands")
        except Exception as e:
            if tui:
                tui.update_data_loading(0, 1, f"Error loading zsh: {str(e)[:50]}")
            else:
                print(f"Warning: Error loading zsh history: {e}")
    
    # Load bash history
    bash_history = home / '.bash_history'
    if bash_history.exists():
        try:
            with open(bash_history, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                current_time = time.time()
                
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Use current time for bash (no timestamps)
                    if current_time > last_timestamp:
                        cursor.execute("""
                            SELECT COUNT(*) FROM actions 
                            WHERE source = 'system' 
                            AND action_type = 'terminal_command'
                            AND context_json LIKE ?
                        """, (f'%"full_command": "{line[:100]}"%',))
                        
                        if cursor.fetchone()[0] == 0:
                            context = {
                                'command': line.split()[0] if line.split() else '',
                                'full_command': line[:500],
                                'shell': 'bash',
                                'category': 'other'
                            }
                            
                            cursor.execute("""
                                INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                                VALUES (?, 'system', 'terminal_command', ?, 'shell_history_import')
                            """, (current_time, json.dumps(context)))
                            actions_added += 1
                            current_time += 1  # Increment to avoid exact duplicates
                            
                            if tui:
                                tui.add_recent_action('terminal_command', 'bash', line[:50])
        except Exception as e:
            pass

    # Load extended developer histories
    if tui:
        tui.update_data_loading(actions_added, actions_added, "Loading git history...")
    git_actions = _load_git_history_from_workspace(cursor, home, tui)
    actions_added += git_actions
    
    if tui:
        tui.update_data_loading(actions_added, actions_added, "Loading npm history...")
    npm_actions = _load_npm_history_from_logs(cursor, home, tui)
    actions_added += npm_actions
    
    if tui:
        tui.update_data_loading(actions_added, actions_added, "Loading pip history...")
    pip_actions = _load_pip_history_from_logs(cursor, home, tui)
    actions_added += pip_actions
    
    if tui:
        tui.update_data_loading(actions_added, actions_added, "Loading Python REPL history...")
    python_actions = _load_python_repl_history(cursor, home, tui)
    actions_added += python_actions
    
    conn.commit()
    conn.close()
    
    if tui:
        summary_parts = []
        if actions_added > 0:
            summary_parts.append(f"Total: {actions_added}")
        if git_actions > 0:
            summary_parts.append(f"Git: {git_actions}")
        if npm_actions > 0:
            summary_parts.append(f"npm: {npm_actions}")
        if pip_actions > 0:
            summary_parts.append(f"pip: {pip_actions}")
        if python_actions > 0:
            summary_parts.append(f"Python: {python_actions}")
        
        summary = " | ".join(summary_parts) if summary_parts else "No new history found"
        tui.update_data_loading(actions_added, actions_added, f"✅ {summary}")
    
    return actions_added


def _discover_git_repos(home: Path, max_repos: int = 20) -> List[Path]:
    """Best-effort discovery of git repositories for history ingestion."""
    search_roots = [
        home / 'Projects',
        home / 'projects',
        home / 'Code',
        home / 'code',
        home / 'workspace',
        home / 'Workspace',
        home / 'dev',
        home / 'Development',
        Path.cwd()
    ]
    repos = []
    seen = set()
    
    for root in search_roots:
        if not root.exists() or str(root) in seen:
            continue
        seen.add(str(root))
        try:
            for git_dir in root.rglob('.git'):
                repo_path = git_dir.parent
                repo_key = str(repo_path)
                if repo_key in seen:
                    continue
                repos.append(repo_path)
                seen.add(repo_key)
                if len(repos) >= max_repos:
                    return repos
        except Exception:
            continue
    
    return repos


def _load_git_history_from_workspace(cursor, home: Path, tui: Optional[TrainingTUI] = None) -> int:
    """Load git commit history as contextual actions."""
    added = 0
    repos = _discover_git_repos(home)
    if tui and repos:
        tui.update_data_loading(0, len(repos), f"Scanning {len(repos)} git repos for history...")
    
    for idx, repo in enumerate(repos):
        try:
            result = subprocess.run(
                ['git', 'log', '-n', '50', '--pretty=format:%ct|%H|%an|%s'],
                capture_output=True,
                text=True,
                timeout=4,
                cwd=repo
            )
            if result.returncode != 0:
                continue
            
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            for line in lines:
                parts = line.split('|', 3)
                if len(parts) < 4:
                    continue
                timestamp_str, commit_hash, author, message = parts
                try:
                    timestamp = int(timestamp_str.strip())
                except:
                    timestamp = int(time.time())
                
                cursor.execute("""
                    SELECT COUNT(*) FROM actions
                    WHERE action_type = 'git_history_commit'
                    AND context_json LIKE ?
                """, (f'%{commit_hash}%',))
                
                if cursor.fetchone()[0]:
                    continue
                
                context = {
                    'repo_path': str(repo),
                    'commit': commit_hash,
                    'author': author,
                    'message': message[:300]
                }
                
                cursor.execute("""
                    INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                    VALUES (?, 'system', 'git_history_commit', ?, 'dev_history_import')
                """, (timestamp, json.dumps(context)))
                added += 1
                
                if tui:
                    tui.add_recent_action('git_history_commit', repo.name, message[:40])
        except Exception:
            continue
        finally:
            if tui:
                tui.update_data_loading(idx + 1, len(repos), f"Git history from {repo.name}")
    
    return added


def _parse_npm_log_command(log_text: str) -> Optional[str]:
    """Extract npm command from a debug log."""
    for line in log_text.splitlines():
        if 'verbose cli [' in line:
            try:
                start = line.index('[')
                end = line.rindex(']') + 1
                cli_array = ast.literal_eval(line[start:end])
                if len(cli_array) >= 3:
                    return f"npm {' '.join(cli_array[2:])}".strip()
            except Exception:
                continue
        if line.strip().startswith('argv "'):
            matches = re.findall(r'"([^"]+)"', line)
            if len(matches) >= 3:
                return 'npm ' + ' '.join(matches[2:])
    return None


def _load_npm_history_from_logs(cursor, home: Path, tui: Optional[TrainingTUI] = None) -> int:
    """Load npm debug log history."""
    logs_dir = home / '.npm/_logs'
    if not logs_dir.exists():
        return 0
    
    added = 0
    log_files = sorted(logs_dir.glob('*-debug.log'), key=lambda p: p.stat().st_mtime)[-40:]
    
    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            command_line = _parse_npm_log_command(content)
            if not command_line:
                continue
            
            command_hash = hashlib.md5(command_line.encode()).hexdigest()[:12]
            cursor.execute("""
                SELECT COUNT(*) FROM actions
                WHERE action_type = 'npm_history_command'
                AND context_json LIKE ?
            """, (f'%{command_hash}%',))
            
            if cursor.fetchone()[0]:
                continue
            
            context = {
                'command': command_line,
                'command_hash': command_hash,
                'log_file': str(log_file)
            }
            
            timestamp = log_file.stat().st_mtime
            cursor.execute("""
                INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                VALUES (?, 'system', 'npm_history_command', ?, 'dev_history_import')
            """, (timestamp, json.dumps(context)))
            added += 1
            
            if tui:
                tui.add_recent_action('npm_history_command', 'npm', command_line[:50])
        except Exception:
            continue
    
    return added


def _load_pip_history_from_logs(cursor, home: Path, tui: Optional[TrainingTUI] = None) -> int:
    """Load pip debug log history."""
    candidates = [
        home / '.cache/pip/pip.log',
        home / '.cache/pip/log/debug.log',
        home / '.pip/pip.log'
    ]
    added = 0
    
    for log_file in candidates:
        if not log_file.exists():
            continue
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-2000:]
        except Exception:
            continue
        
        for line in lines:
            if 'Running command' not in line:
                continue
            
            command = line.split('Running command', 1)[1].strip()
            if not command:
                continue
            
            cmd_hash = hashlib.md5(command.encode()).hexdigest()[:12]
            cursor.execute("""
                SELECT COUNT(*) FROM actions
                WHERE action_type = 'pip_history_command'
                AND context_json LIKE ?
            """, (f'%{cmd_hash}%',))
            
            if cursor.fetchone()[0]:
                continue
            
            timestamp = log_file.stat().st_mtime
            match = re.match(r'(\d{4}-\d{2}-\d{2}T[\d:.+-]+)', line)
            if match:
                try:
                    timestamp = datetime.fromisoformat(match.group(1)).timestamp()
                except Exception:
                    timestamp = log_file.stat().st_mtime
            
            context = {
                'command': command,
                'command_hash': cmd_hash,
                'log_file': str(log_file)
            }
            
            cursor.execute("""
                INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
                VALUES (?, 'system', 'pip_history_command', ?, 'dev_history_import')
            """, (timestamp, json.dumps(context)))
            added += 1
            
            if tui:
                tui.add_recent_action('pip_history_command', 'pip', command[:50])
    
    return added


def _load_python_repl_history(cursor, home: Path, tui: Optional[TrainingTUI] = None) -> int:
    """Load Python REPL commands from ~/.python_history."""
    history_file = home / '.python_history'
    if not history_file.exists():
        return 0
    
    added = 0
    try:
        with open(history_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-5000:]
    except Exception:
        return 0
    
    for line in lines:
        command = line.strip()
        if not command:
            continue
        
        cmd_hash = hashlib.md5(command.encode()).hexdigest()[:12]
        cursor.execute("""
            SELECT COUNT(*) FROM actions
            WHERE action_type = 'python_repl_command'
            AND context_json LIKE ?
        """, (f'%{cmd_hash}%',))
        
        if cursor.fetchone()[0]:
            continue
        
        context = {
            'code': command[:500],
            'command_hash': cmd_hash,
            'source_file': str(history_file)
        }
        
        cursor.execute("""
            INSERT INTO actions (timestamp, source, action_type, context_json, session_id)
            VALUES (?, 'system', 'python_repl_command', ?, 'dev_history_import')
        """, (time.time(), json.dumps(context)))
        added += 1
        
        if tui:
            tui.add_recent_action('python_repl_command', 'python', command[:50])
    
    return added


def load_trajectories_from_db(db_path: str, min_actions: int = 100, 
                              last_training_timestamp: float = None,
                              tui: Optional[TrainingTUI] = None):
    """
    Load expert trajectories from database.
    
    Args:
        db_path: Path to SQLite database
        min_actions: Minimum number of actions required
        last_training_timestamp: Only load actions after this timestamp (for incremental training)
        tui: Optional TUI for progress updates
        
    Returns:
        Tuple of (trajectories, metadata_dict)
    """
    if tui:
        tui.update_data_loading(0, 1, f"Connecting to database...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Filter out high-frequency/noisy actions that bloat the neural network
    FILTERED_ACTION_TYPES = {
        'dom_change',
        'mouse_move',
        'mouse_enter',
        'mouse_leave',
    }
    
    # Build query with optional timestamp filter
    placeholders = ','.join(['?' for _ in FILTERED_ACTION_TYPES])
    if last_training_timestamp:
        query = f"""
            SELECT id, timestamp, source, action_type, context_json
            FROM actions
            WHERE action_type NOT IN ({placeholders})
            AND timestamp > ?
            ORDER BY timestamp ASC
        """
        params = tuple(FILTERED_ACTION_TYPES) + (last_training_timestamp,)
    else:
        query = f"""
            SELECT id, timestamp, source, action_type, context_json
            FROM actions
            WHERE action_type NOT IN ({placeholders})
            ORDER BY timestamp ASC
        """
        params = tuple(FILTERED_ACTION_TYPES)
    
    if tui:
        tui.update_data_loading(0, 1, "Querying database...")
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    if len(rows) < min_actions:
        conn.close()
        raise ValueError(
            f"Not enough data! Found {len(rows)} actions (after filtering), need at least {min_actions}.\n"
            f"Keep using the system to collect more data."
        )
    
    # Extract metadata
    first_action_id = rows[0][0]
    last_action_id = rows[-1][0]
    first_timestamp = rows[0][1]
    last_timestamp = rows[-1][1]
    total_actions = len(rows)
    
    # Get unique sources
    sources = set(row[2] for row in rows)
    
    # Count by source and action type
    source_counts = {}
    action_type_counts = {}
    for row in rows:
        source = row[2]
        action_type = row[3]
        source_counts[source] = source_counts.get(source, 0) + 1
        action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1
    
    metadata = {
        'first_action_id': first_action_id,
        'last_action_id': last_action_id,
        'first_timestamp': first_timestamp,
        'last_timestamp': last_timestamp,
        'total_actions': total_actions,
        'sources': list(sources)
    }
    
    if tui:
        if last_training_timestamp:
            tui.update_data_loading(0, total_actions, f"Found {total_actions:,} NEW actions (incremental training)")
        else:
            tui.update_data_loading(0, total_actions, f"Found {total_actions:,} actions (full training)")
        tui.set_total_actions(total_actions)
        # Update TUI with data breakdown
        tui.data_sources = source_counts
        tui.data_action_types = action_type_counts
    
    # Initialize feature extractor
    extractor = FeatureExtractor()
    
    # Build trajectories
    trajectory = []
    
    if tui:
        tui.update_data_loading(0, total_actions, "Extracting features...")
    
    for i, (action_id, timestamp, source, action_type, context_json) in enumerate(rows):
        try:
            context = json.loads(context_json) if context_json else {}
        except:
            context = {}
        
        action_data = {
            'timestamp': timestamp,
            'source': source,
            'action_type': action_type,
            'context': context
        }
        
        # Extract state vector (before this action)
        state = extractor.extract_state_vector()
        
        # Extract action vector (for this action)
        action = extractor.extract_action_vector(action_data)
        
        trajectory.append((state, action))
        
        # Update extractor with this action (for next state)
        extractor.update_from_action(action_data)
        
        if tui and (i + 1) % 100 == 0:
            tui.update_data_loading(i + 1, total_actions, f"Processing {i+1:,}/{total_actions:,} actions...")
    
    if tui:
        tui.update_data_loading(total_actions, total_actions, f"✅ Created trajectory with {len(trajectory)} state-action pairs")
    
    # Return as list of trajectories (for now, just one) and metadata
    return [trajectory], metadata


class TrainingCallback:
    """Callback for training progress updates."""
    
    def __init__(self, tui: TrainingTUI):
        self.tui = tui
        self.tui.training_start_time = time.time()
    
    def __call__(self, epoch: int, total_epochs: int, loss: float = None,
                reward_mean: float = None, reward_std: float = None):
        """Update TUI with training metrics."""
        self.tui.update_training(epoch, total_epochs, loss, reward_mean, reward_std)


def train_model(
    db_path: str,
    num_epochs: int = 50,
    learning_rate: float = 0.001,
    batch_size: int = 64,
    checkpoint_dir: Path = None,
    last_training_timestamp: float = None,
    tui: Optional[TrainingTUI] = None
):
    """
    Train IRL model with beautiful TUI.
    
    Args:
        db_path: Path to database
        num_epochs: Number of training epochs
        learning_rate: Learning rate
        batch_size: Batch size
        checkpoint_dir: Directory to save checkpoints
        last_training_timestamp: Only train on data after this timestamp (for incremental training)
        tui: Optional TUI for progress display
        
    Returns:
        Tuple of (irl_model, history, metadata_dict)
    """
    if tui:
        tui.training_status = "Loading data..."
        tui.training_start_time = time.time()
    
    # Load trajectories with metadata
    try:
        trajectories, data_metadata = load_trajectories_from_db(
            db_path, min_actions=100, 
            last_training_timestamp=last_training_timestamp,
            tui=tui
        )
    except ValueError as e:
        if tui:
            tui.training_status = f"❌ Error: {str(e)[:50]}"
        else:
            print(f"❌ Error: {e}")
        return None, None, None
    
    # Initialize IRL algorithm
    if tui:
        tui.training_status = "Initializing model..."
    
    irl = MaxEntIRL(
        state_dim=192,
        action_dim=48,
        learning_rate=learning_rate
    )
    
    # Create callback for progress updates
    callback = TrainingCallback(tui) if tui else None
    
    # Train with TUI
    if tui:
        tui.training_status = "Training..."
    
    # Train with callback support, early stopping, and validation
    # For large datasets (50k+ actions), use validation and early stopping
    # For smaller datasets, train longer without validation
    total_actions = len(trajectories) if trajectories else 0
    if total_actions > 0:
        # Estimate total state-action pairs (roughly 1 per trajectory entry)
        estimated_pairs = sum(len(traj) for traj in trajectories)
    else:
        estimated_pairs = 0
    
    # Adaptive training parameters based on dataset size
    if estimated_pairs > 50000:
        # Large dataset: use validation and early stopping
        validation_split = 0.1
        early_stopping_patience = 15  # More patience for large datasets
        recommended_epochs = min(num_epochs, 100)  # Cap at 100 for large datasets
        if tui:
            tui.console.print(f"[yellow]📊 Large dataset detected ({estimated_pairs:,} pairs)[/yellow]")
            tui.console.print(f"[dim]   Using validation split (10%) and early stopping (patience: {early_stopping_patience})[/dim]")
    elif estimated_pairs > 10000:
        # Medium dataset: moderate validation
        validation_split = 0.15
        early_stopping_patience = 12
        recommended_epochs = num_epochs
    else:
        # Small dataset: no validation, train longer
        validation_split = 0.0
        early_stopping_patience = 20
        recommended_epochs = max(num_epochs, 50)  # At least 50 epochs for small datasets
        if tui:
            tui.console.print(f"[yellow]📊 Small dataset ({estimated_pairs:,} pairs)[/yellow]")
            tui.console.print(f"[dim]   Training without validation, will use early stopping if loss plateaus[/dim]")
    
    history = irl.train(
        expert_trajectories=trajectories,
        num_epochs=recommended_epochs,
        batch_size=batch_size,
        verbose=not bool(tui),  # Verbose only if no TUI
        callback=callback,  # Pass callback for TUI updates
        early_stopping_patience=early_stopping_patience,
        min_loss_delta=1e-6,
        validation_split=validation_split
    )
    
    # Save model
    if checkpoint_dir is None:
        checkpoint_dir = project_root / 'models' / 'checkpoints'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    checkpoint_path = checkpoint_dir / f'reward_model_{timestamp}.pt'
    
    if tui:
        tui.training_status = "Saving model..."
    
    irl.save_model(str(checkpoint_path))
    
    # Add model path to metadata
    data_metadata['model_path'] = str(checkpoint_path)
    data_metadata['final_loss'] = history['loss'][-1] if history.get('loss') else None
    data_metadata['final_reward_mean'] = history['reward_mean'][-1] if history.get('reward_mean') else None
    data_metadata['final_reward_std'] = history['reward_std'][-1] if history.get('reward_std') else None
    data_metadata['num_epochs'] = num_epochs
    data_metadata['learning_rate'] = learning_rate
    data_metadata['batch_size'] = batch_size
    data_metadata['started_at'] = time.time()
    data_metadata['completed_at'] = time.time()
    
    if tui:
        tui.training_status = "✅ Training Complete!"
        tui.completed = True
        tui.completion_summary = {
            'model_path': str(checkpoint_path),
            'final_loss': data_metadata['final_loss'],
            'final_reward_mean': data_metadata['final_reward_mean'],
            'final_reward_std': data_metadata['final_reward_std'],
            'num_epochs': num_epochs,
            'total_actions': data_metadata['total_actions'],
            'sources': data_metadata['sources'],
            'data_range': f"{datetime.fromtimestamp(data_metadata['first_timestamp']).strftime('%Y-%m-%d %H:%M')} to {datetime.fromtimestamp(data_metadata['last_timestamp']).strftime('%Y-%m-%d %H:%M')}"
        }
        tui.new_data_summary = {
            'total_actions': data_metadata['total_actions'],
            'sources_breakdown': {s: tui.data_sources.get(s, 0) for s in data_metadata['sources']},
            'action_types': dict(list(tui.data_action_types.items())[:10])
        }
        # Update to 100% progress
        tui.update_training(num_epochs, num_epochs, data_metadata['final_loss'], 
                           data_metadata['final_reward_mean'], data_metadata['final_reward_std'])
    
    # Output metadata as JSON for backend to parse
    if not tui:
        print(f"\n📊 TRAINING_METADATA_JSON: {json.dumps(data_metadata)}")
    
    return irl, history, data_metadata


if __name__ == '__main__':
    # Check if rich is available
    use_tui = HAS_RICH
    
    # Create TUI
    tui = TrainingTUI() if use_tui else None
    
    # Load config
    config = load_config()
    db_config = config['database']
    db_path = db_config['path']
    
    # Resolve database path relative to project root
    if not Path(db_path).is_absolute():
        db_path = project_root / db_path
    
    # Ensure database exists, create if needed
    if not Path(db_path).exists():
        if tui:
            tui.update_data_loading(0, 1, "Database not found, creating...")
        # Create database with schema
        from database.schema import create_tables
        from database import DatabaseManager
        db_manager = DatabaseManager(db_path)
        create_tables(db_manager.connect())
        db_manager.close()
    
    # Load shell history if backend hasn't been running
    if tui:
        tui.update_data_loading(0, 1, "📚 Scanning for shell history files...")
        tui.console.print("\n[bold cyan]📚 Loading Historical Data[/bold cyan]")
        tui.console.print("[dim]This includes: zsh, bash, git, npm, pip, Python REPL history[/dim]\n")
    
    shell_actions = load_shell_history_to_db(str(db_path), tui)
    if shell_actions > 0:
        if tui:
            tui.console.print(f"[green]✅ Loaded {shell_actions:,} historical commands[/green]\n")
        else:
            print(f"✅ Loaded {shell_actions:,} shell commands from history")
    elif tui:
        tui.console.print("[yellow]⚠️  No new shell history found (may already be in DB)[/yellow]\n")
    
    # Training config - check environment variables first (from API), then config file
    import os
    
    # Load data first to make smart recommendations
    db_manager = DatabaseManager(db_path)
    conn = db_manager.connect()
    cursor = conn.cursor()
    
    # Get dataset size for smart defaults
    cursor.execute("SELECT COUNT(*) FROM actions WHERE action_type NOT IN ('dom_change', 'mouse_move', 'mouse_enter', 'mouse_leave')")
    total_actions = cursor.fetchone()[0]
    conn.close()
    
    # Smart defaults based on dataset size
    if total_actions > 50000:
        recommended_lr = 0.0005  # Lower LR for large datasets (more stable)
        recommended_batch = 128  # Larger batch for large datasets
        recommended_epochs = 80
        lr_explanation = "Large dataset → lower LR for stability"
    elif total_actions > 20000:
        recommended_lr = 0.001  # Standard LR
        recommended_batch = 64
        recommended_epochs = 60
        lr_explanation = "Medium dataset → standard LR"
    else:
        recommended_lr = 0.002  # Higher LR for small datasets (faster learning)
        recommended_batch = 32
        recommended_epochs = 50
        lr_explanation = "Small dataset → higher LR for faster learning"
    
    # Ask user for training parameters if not set via environment
    if not os.environ.get('TRAINING_EPOCHS'):
        if tui and HAS_RICH:
            tui.console.print("\n[bold cyan]Training Configuration[/bold cyan]")
            tui.console.print(f"[dim]Dataset: {total_actions:,} actions → {lr_explanation}[/dim]\n")
            
            try:
                epochs_input = tui.console.input(f"[cyan]Number of epochs[/cyan] (recommended: {recommended_epochs}, default: 50): ").strip()
                num_epochs = int(epochs_input) if epochs_input else recommended_epochs
            except ValueError:
                num_epochs = recommended_epochs
                tui.console.print(f"[yellow]Invalid input, using recommended: {recommended_epochs}[/yellow]")
            
            try:
                batch_input = tui.console.input(f"[cyan]Batch size[/cyan] (recommended: {recommended_batch}, default: 64): ").strip()
                batch_size = int(batch_input) if batch_input else recommended_batch
            except ValueError:
                batch_size = recommended_batch
                tui.console.print(f"[yellow]Invalid input, using recommended: {recommended_batch}[/yellow]")
            
            try:
                lr_input = tui.console.input(f"[cyan]Learning rate[/cyan] (recommended: {recommended_lr}, default: 0.001) [dim]Press Enter for smart default[/dim]: ").strip()
                learning_rate = float(lr_input) if lr_input else recommended_lr
            except ValueError:
                learning_rate = recommended_lr
                tui.console.print(f"[yellow]Invalid input, using recommended: {recommended_lr}[/yellow]")
            
            if not lr_input:
                tui.console.print(f"[green]✓ Using smart default: {recommended_lr} (based on {total_actions:,} actions)[/green]")
        else:
            # Basic input without rich
            print(f"\n📊 Dataset: {total_actions:,} actions")
            print(f"💡 Recommended: LR={recommended_lr}, Batch={recommended_batch}, Epochs={recommended_epochs}")
            try:
                epochs_input = input(f"\nNumber of epochs (recommended: {recommended_epochs}, default: 50): ").strip()
                num_epochs = int(epochs_input) if epochs_input else recommended_epochs
            except (ValueError, EOFError):
                num_epochs = recommended_epochs
            
            try:
                batch_input = input(f"Batch size (recommended: {recommended_batch}, default: 64): ").strip()
                batch_size = int(batch_input) if batch_input else recommended_batch
            except (ValueError, EOFError):
                batch_size = recommended_batch
            
            try:
                lr_input = input(f"Learning rate (recommended: {recommended_lr}, default: 0.001) [Press Enter for smart default]: ").strip()
                learning_rate = float(lr_input) if lr_input else recommended_lr
                if not lr_input:
                    print(f"✓ Using smart default: {recommended_lr}")
            except (ValueError, EOFError):
                learning_rate = recommended_lr
    else:
        # Use environment variables or config defaults
        num_epochs = int(os.environ.get('TRAINING_EPOCHS', 0)) or config.get('training', {}).get('num_epochs', recommended_epochs)
        learning_rate = float(os.environ.get('TRAINING_LR', 0)) or config.get('training', {}).get('learning_rate', recommended_lr)
        batch_size = int(os.environ.get('TRAINING_BATCH_SIZE', 0)) or config.get('training', {}).get('batch_size', recommended_batch)
    
    # Train with TUI
    try:
        if use_tui:
            def generate_layout():
                return tui.render()
            
            with Live(generate_layout(), refresh_per_second=10, screen=False) as live:
                def update_ui():
                    while not tui.stop_event.is_set():
                        live.update(generate_layout())
                        time.sleep(0.1)
                
                update_thread = Thread(target=update_ui, daemon=True)
                update_thread.start()
                
                try:
                    irl, history, metadata = train_model(
                        db_path=str(db_path),
                        num_epochs=num_epochs,
                        learning_rate=learning_rate,
                        batch_size=batch_size,
                        tui=tui
                    )
                    
                    tui.stop_event.set()
                    # Show completion screen for 5 seconds
                    for _ in range(50):  # 5 seconds at 10fps
                        live.update(generate_layout())
                        time.sleep(0.1)
                    
                    # Clear screen and show final summary
                    live.stop()
                    tui.console.clear()
                    
                    if irl:
                        # Show beautiful completion summary
                        summary_table = Table(show_header=False, box=box.ROUNDED, border_style="green")
                        summary_table.add_column(style="bold cyan", width=20)
                        summary_table.add_column(style="white", width=60)
                        
                        summary_table.add_row("", Text("🎉 Training Complete!", style="bold green"))
                        summary_table.add_row("", "")
                        summary_table.add_row("Model Path:", metadata['model_path'])
                        summary_table.add_row("", "")
                        summary_table.add_row(Text("Final Metrics:", style="bold"), "")
                        summary_table.add_row("  Loss:", f"{metadata['final_loss']:.6f}")
                        summary_table.add_row("  Reward μ:", f"{metadata['final_reward_mean']:.4f}")
                        summary_table.add_row("  Reward σ:", f"{metadata['final_reward_std']:.4f}")
                        summary_table.add_row("", "")
                        summary_table.add_row(Text("Training Config:", style="bold"), "")
                        summary_table.add_row("  Epochs:", str(num_epochs))
                        summary_table.add_row("  Batch Size:", str(batch_size))
                        summary_table.add_row("  Learning Rate:", str(learning_rate))
                        summary_table.add_row("", "")
                        summary_table.add_row(Text("Data Used:", style="bold"), "")
                        summary_table.add_row("  Total Actions:", f"{metadata['total_actions']:,}")
                        summary_table.add_row("  Sources:", ", ".join(metadata['sources']))
                        summary_table.add_row("  Data Range:", f"{datetime.fromtimestamp(metadata['first_timestamp']).strftime('%Y-%m-%d %H:%M')} to {datetime.fromtimestamp(metadata['last_timestamp']).strftime('%Y-%m-%d %H:%M')}")
                        
                        summary_panel = Panel(summary_table, title="Training Summary", border_style="green")
                        tui.console.print(summary_panel)
                        tui.console.print(f"\n[bold green]✅ Model ready for predictions![/bold green]")
                except KeyboardInterrupt:
                    tui.stop_event.set()
                    tui.console.print("\n[yellow]Training interrupted by user[/yellow]")
                finally:
                    tui.stop_event.set()
        else:
            # Basic training without TUI
            irl, history, metadata = train_model(
                db_path=str(db_path),
                num_epochs=num_epochs,
                learning_rate=learning_rate,
                batch_size=batch_size,
                tui=None
            )
            
            if irl:
                print("🎉 Success! Model is ready for predictions.")
                print(f"Model saved to: {metadata['model_path']}")
    except Exception as e:
        if tui:
            tui.console.print(f"\n[bold red]❌ Training failed: {e}[/bold red]")
        else:
            print(f"\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
