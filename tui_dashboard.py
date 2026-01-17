"""
KrypticTrack - Comprehensive TUI Dashboard

A beautiful terminal interface for your "laptop brain"
- Daily summaries with LLM narration
- Goal management and alignment
- Session tracking and time breakdowns
- Interactive LLM chat
"""

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text
from rich import box
from datetime import datetime, timedelta
import time
import sys
from pathlib import Path

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
from backend.services.productivity_patterns import get_productivity_pattern_analyzer
from backend.services.distraction_tracker import get_distraction_tracker
from backend.services.heatmap_generator import get_heatmap_generator


class KrypticTrackTUI:
    """Main TUI application."""
    
    def __init__(self):
        """Initialize TUI."""
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
        self.productivity_analyzer = get_productivity_pattern_analyzer(self.conn)
        self.distraction_tracker = get_distraction_tracker(self.conn)
        self.heatmap_gen = get_heatmap_generator(self.conn)
        
        # State
        self.current_view = "home"
        self.selected_date = datetime.now().strftime('%Y-%m-%d')
        self.running = True
    
    def show_header(self):
        """Display header."""
        header = Text()
        header.append("🧠 ", style="bold cyan")
        header.append("KrypticTrack", style="bold white")
        header.append(" - Your Laptop Brain", style="dim")
        
        status = "🟢 Online" if self.llm.is_available() else "🔴 LLM Offline"
        date_str = datetime.now().strftime("%B %d, %Y - %H:%M")
        
        panel = Panel(
            header,
            subtitle=f"{date_str} | {status}",
            border_style="cyan",
            box=box.DOUBLE
        )
        self.console.print(panel)
    
    def show_menu(self):
        """Display main menu."""
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column(style="cyan bold")
        menu.add_column(style="white")
        
        menu.add_row("1", "📅 Daily Summary")
        menu.add_row("2", "🎯 Goals & Alignment")
        menu.add_row("3", "⏱️  Sessions & Time Tracking")
        menu.add_row("4", "💬 Chat with LLM")
        menu.add_row("5", "📊 Quick Stats")
        menu.add_row("6", "📈 Productivity Insights")
        menu.add_row("q", "🚪 Quit")
        
        self.console.print(Panel(menu, title="[bold cyan]Main Menu", border_style="cyan"))
    
    def view_daily_summary(self):
        """Show daily summary view."""
        self.console.clear()
        self.show_header()
        
        self.console.print(f"\n[bold cyan]📅 Daily Summary - {self.selected_date}[/]\n")
        
        # Show loading
        with self.console.status("[cyan]Generating summary with LLM...", spinner="dots"):
            try:
                summary = self.summary_gen.generate_summary(self.selected_date, use_llm=True)
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/]")
                self.console.print("\n[dim]Press Enter to continue...[/]")
                input()
                return
        
        # Create main layout with 2 columns
        layout = Layout()
        layout.split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=3)
        )
        
        # Left: Stats
        stats_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        stats_table.add_column(style="bold cyan", width=20)
        stats_table.add_column(style="white", justify="right")
        
        # Calculate total session time for clarity
        total_session_time_seconds = sum(
            data.get('total_seconds', data['total_minutes'] * 60)
            for data in summary['sessions']['by_type'].values()
        )
        total_session_hours = total_session_time_seconds / 3600
        total_session_formatted = f"{int(total_session_hours)}h {int((total_session_time_seconds % 3600)/60)}m"
        
        stats_table.add_row("⏱️  Total Session Time", f"[bold green]{total_session_formatted}[/]")
        stats_table.add_row("📊 Work Sessions", f"[bold]{summary['sessions']['count']}[/]")
        stats_table.add_row("🎯 Focus Score", f"[bold]{summary['productivity']['focus_score']:.0f}[/bold]/100")
        stats_table.add_row("🔄 Context Switches", f"[bold]{summary['productivity']['context_switches']}[/]")
        
        if summary['productivity']['deep_work_periods']:
            deep_work_total = sum(p['duration_minutes'] for p in summary['productivity']['deep_work_periods'])
            stats_table.add_row("🔥 Deep Work Time", f"[bold magenta]{deep_work_total:.0f}m[/]")
        
        stats_panel = Panel(stats_table, title="[bold cyan]📊 Overview", border_style="cyan", box=box.ROUNDED)
        layout["left"].update(stats_panel)
        
        # Right: Session breakdown by type
        session_table = Table(box=box.SIMPLE, padding=(0, 2))
        session_table.add_column("Session Type", style="bold")
        session_table.add_column("Count", justify="center", style="cyan")
        session_table.add_column("Time", justify="right", style="green")
        
        for session_type, data in sorted(summary['sessions']['by_type'].items(), 
                                        key=lambda x: x[1].get('total_seconds', x[1]['total_minutes']*60), 
                                        reverse=True):
            type_emoji = {
                'coding': '💻',
                'research': '🔍', 
                'debugging': '🐛',
                'mixed': '🔀'
            }.get(session_type, '•')
            
            seconds = data.get('total_seconds', data['total_minutes'] * 60)
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            session_table.add_row(
                f"{type_emoji} {session_type.title()}",
                str(data['count']),
                time_str
            )
        
        if session_table.row_count == 0:
            session_table.add_row("No sessions", "-", "-")
        
        session_panel = Panel(session_table, title="[bold magenta]🎯 Session Breakdown", border_style="magenta", box=box.ROUNDED)
        layout["right"].update(session_panel)
        
        self.console.print(layout)
        self.console.print()  # Spacer
        
        # Top projects
        if summary['sessions']['top_projects']:
            proj_table = Table(box=box.SIMPLE, padding=(0, 2))
            proj_table.add_column("Project", style="cyan bold")
            proj_table.add_column("Time", style="green", justify="right")
            proj_table.add_column("% of Total", style="yellow", justify="right")
            
            for proj in summary['sessions']['top_projects'][:5]:
                percentage = (proj['minutes'] / (total_session_time_seconds / 60)) * 100 if total_session_time_seconds > 0 else 0
                proj_table.add_row(
                    proj['project'][:30],
                    f"{proj['hours']:.1f}h",
                    f"{percentage:.0f}%"
                )
            
            self.console.print(Panel(proj_table, title="[bold]🚀 Top Projects", border_style="blue", box=box.ROUNDED))
        
        # Top apps
        if summary['time_breakdown']['by_app']:
            app_table = Table(box=box.SIMPLE, border_style="magenta")
            app_table.add_column("App", style="cyan")
            app_table.add_column("Time", style="green", justify="right")
            
            for app in summary['time_breakdown']['by_app'][:5]:
                app_table.add_row(app['app'], app.get('formatted', str(app['hours']) + 'h'))
            
            self.console.print(Panel(app_table, title="[bold]💻 Top Apps", border_style="magenta"))
        
        # LLM Narrative
        if summary.get('narrative'):
            # Remove <think> tags for cleaner display
            narrative = summary['narrative']
            if '<think>' in narrative:
                # Extract just the final output after thinking
                parts = narrative.split('</think>')
                if len(parts) > 1:
                    narrative = parts[1].strip()
            
            md = Markdown(narrative)
            self.console.print(Panel(
                md,
                title="[bold]🤖 AI Narrative",
                border_style="yellow",
                padding=(1, 2)
            ))
        
        # Goal alignment
        if summary.get('goals'):
            goal_table = Table(box=box.SIMPLE, border_style="green")
            goal_table.add_column("Goal", style="white")
            goal_table.add_column("Alignment", style="cyan", justify="right")
            
            for goal_info in summary['goals']:
                alignment = goal_info['alignment'].get('alignment_percentage', 0)
                emoji = "✅" if alignment >= 70 else "⚠️" if alignment >= 40 else "❌"
                goal_table.add_row(
                    goal_info['goal'][:50],
                    f"{emoji} {alignment:.0f}%"
                )
            
            self.console.print(Panel(goal_table, title="[bold]🎯 Goal Alignment", border_style="green"))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def view_goals(self):
        """Show goals management view."""
        while True:
            self.console.clear()
            self.show_header()
            
            self.console.print("\n[bold cyan]🎯 Goals & Alignment[/]\n")
            
            # Get active goals
            goals = self.goal_service.get_active_goals()
            
            if not goals:
                self.console.print("[yellow]No goals set yet![/]\n")
            else:
                goal_table = Table(box=box.ROUNDED, border_style="cyan")
                goal_table.add_column("#", style="dim")
                goal_table.add_column("Goal", style="white")
                goal_table.add_column("Category", style="cyan")
                goal_table.add_column("Keywords", style="green")
                
                for i, goal in enumerate(goals, 1):
                    keywords = ', '.join(goal['keywords'][:3])
                    if len(goal['keywords']) > 3:
                        keywords += "..."
                    goal_table.add_row(
                        str(i),
                        goal['goal_text'][:60],
                        goal['category'],
                        keywords
                    )
                
                self.console.print(goal_table)
            
            # Menu
            self.console.print("\n[cyan]1[/] Add Goal | [cyan]2[/] Check Alignment | [cyan]b[/] Back")
            choice = Prompt.ask("Select", default="b")
            
            if choice == "1":
                self.add_goal()
            elif choice == "2" and goals:
                self.check_goal_alignment(goals)
            elif choice == "b":
                break
    
    def add_goal(self):
        """Add a new goal."""
        self.console.print("\n[bold cyan]➕ Add New Goal[/]\n")
        
        goal_text = Prompt.ask("Goal description")
        if not goal_text:
            return
        
        keywords_str = Prompt.ask("Keywords (comma-separated)")
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        
        category = Prompt.ask(
            "Category",
            choices=["career", "learning", "project", "habit", "general"],
            default="general"
        )
        
        goal_id = self.goal_service.create_goal(goal_text, keywords, category=category)
        
        self.console.print(f"\n[green]✅ Goal created (ID: {goal_id})[/]")
        time.sleep(1)
    
    def check_goal_alignment(self, goals):
        """Check alignment for a specific goal."""
        goal_num = Prompt.ask("Goal number", default="1")
        try:
            goal_idx = int(goal_num) - 1
            if goal_idx < 0 or goal_idx >= len(goals):
                return
            
            goal = goals[goal_idx]
            
            self.console.print(f"\n[bold]Checking alignment for: {goal['goal_text']}[/]\n")
            
            timeframe = Prompt.ask(
                "Timeframe",
                choices=["day", "week", "month"],
                default="week"
            )
            
            # Calculate alignment
            with self.console.status("[cyan]Calculating alignment..."):
                now = time.time()
                if timeframe == 'day':
                    start_time = now - (24 * 3600)
                elif timeframe == 'week':
                    start_time = now - (7 * 24 * 3600)
                else:
                    start_time = now - (30 * 24 * 3600)
                
                alignment = self.goal_service.check_alignment(goal['id'], start_time, now)
                feedback = self.goal_service.generate_feedback(goal['id'], timeframe)
            
            # Display results
            result_table = Table(show_header=False, box=box.ROUNDED, border_style="cyan")
            result_table.add_column(style="bold white")
            result_table.add_column(style="green")
            
            result_table.add_row("Total Actions", str(alignment['total_actions']))
            result_table.add_row("Relevant Actions", str(alignment['relevant_actions']))
            result_table.add_row("Alignment", f"{alignment['alignment_percentage']}%")
            result_table.add_row("Time Spent", f"{alignment['time_spent_hours']:.1f}h")
            
            self.console.print(Panel(result_table, title="[bold]Alignment Stats", border_style="cyan"))
            self.console.print(f"\n{feedback}\n")
            
            self.console.print("[dim]Press Enter to continue...[/]")
            input()
        except ValueError:
            pass
    
    def view_sessions(self):
        """Show sessions and time tracking."""
        self.console.clear()
        self.show_header()
        
        self.console.print(f"\n[bold cyan]⏱️  Sessions & Time Tracking - {self.selected_date}[/]\n")
        
        # Get sessions
        with self.console.status("[cyan]Loading sessions..."):
            sessions = self.session_detector.get_sessions_for_day(self.selected_date)
            
            dt = datetime.strptime(self.selected_date, '%Y-%m-%d')
            start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
            end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
            
            deep_work = self.time_tracker.detect_deep_work(start_of_day, end_of_day)
        
        # Sessions table
        if sessions:
            sess_table = Table(box=box.ROUNDED, border_style="cyan")
            sess_table.add_column("Time", style="cyan")
            sess_table.add_column("Duration", style="green")
            sess_table.add_column("Type", style="yellow")
            sess_table.add_column("Project", style="magenta")
            sess_table.add_column("Actions", style="white", justify="right")
            
            for sess in sessions[:10]:
                start_time = datetime.fromtimestamp(sess['start_time']).strftime('%H:%M')
                sess_table.add_row(
                    start_time,
                    f"{sess['duration_minutes']:.0f}m",
                    sess['session_type'],
                    sess['project'] or "—",
                    str(sess['action_count'])
                )
            
            self.console.print(Panel(sess_table, title="[bold]📊 Work Sessions", border_style="cyan"))
        else:
            self.console.print("[yellow]No sessions found for this date[/]\n")
        
        # Deep work periods
        if deep_work:
            dw_table = Table(box=box.SIMPLE, border_style="green")
            dw_table.add_column("Duration", style="green")
            dw_table.add_column("Project", style="cyan")
            
            for dw in deep_work[:5]:
                dw_table.add_row(
                    f"{dw['duration_minutes']:.0f}m",
                    dw['project'] or "—"
                )
            
            self.console.print(Panel(
                dw_table,
                title=f"[bold]🔥 Deep Work ({len(deep_work)} periods)",
                border_style="green"
            ))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def chat_with_llm(self):
        """Interactive LLM chat."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]💬 Chat with Your Laptop Brain[/]\n")
        
        if not self.llm.is_available():
            self.console.print("[red]❌ LLM is not available. Please start LM Studio.[/]\n")
            self.console.print("[dim]Press Enter to continue...[/]")
            input()
            return
        
        self.console.print("[green]✅ Connected to LM Studio[/]")
        self.console.print("[dim]Type 'exit' to return to menu[/]\n")
        
        # Load user context
        self.llm.load_user_context(self.conn)
        
        while True:
            question = Prompt.ask("\n[bold cyan]You[/]")
            
            if question.lower() in ['exit', 'quit', 'back']:
                break
            
            if not question.strip():
                continue
            
            # Get LLM response
            with self.console.status("[cyan]Thinking..."):
                try:
                    response = self.llm.chat(question, intent='analysis')
                except Exception as e:
                    self.console.print(f"[red]Error: {e}[/]")
                    continue
            
            # Clean up thinking tags
            if '<think>' in response:
                parts = response.split('</think>')
                if len(parts) > 1:
                    response = parts[1].strip()
            
            # Display response
            self.console.print(Panel(
                Markdown(response),
                title="[bold green]🤖 AI",
                border_style="green",
                padding=(1, 2)
            ))
    
    def show_quick_stats(self):
        """Show quick statistics."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]📊 Quick Statistics[/]\n")
        
        with self.console.status("[cyan]Loading stats..."):
            # Get counts
            cursor = self.conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM actions")
            total_actions = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT source) FROM actions")
            unique_sources = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM user_goals WHERE status='active'")
            active_goals = cursor.fetchone()[0]
            
            # Today's actions
            today = datetime.now().strftime('%Y-%m-%d')
            dt = datetime.strptime(today, '%Y-%m-%d')
            start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
            end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
            
            cursor.execute("""
                SELECT COUNT(*) FROM actions
                WHERE timestamp >= ? AND timestamp <= ?
            """, (start_of_day, end_of_day))
            today_actions = cursor.fetchone()[0]
        
        # Display stats
        stats = Table(show_header=False, box=box.DOUBLE_EDGE, border_style="cyan")
        stats.add_column(style="bold white", width=30)
        stats.add_column(style="bold green", justify="right", width=15)
        
        stats.add_row("📊 Total Actions Logged", f"{total_actions:,}")
        stats.add_row("📅 Today's Actions", f"{today_actions:,}")
        stats.add_row("🔌 Data Sources", str(unique_sources))
        stats.add_row("🎯 Active Goals", str(active_goals))
        stats.add_row("🧠 LM Studio", "🟢 Online" if self.llm.is_available() else "🔴 Offline")
        
        self.console.print(Panel(stats, title="[bold]System Overview", border_style="cyan"))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def view_productivity_insights(self):
        """Show productivity insights with heatmaps and analysis."""
        while True:
            self.console.clear()
            self.show_header()
            
            self.console.print("\n[bold cyan]📈 Productivity Insights[/]\n")
            
            # Submenu
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column(style="cyan bold")
            menu.add_column(style="white")
            
            menu.add_row("1", "🔥 Weekly Heatmap")
            menu.add_row("2", "🎯 Peak Performance Hours")
            menu.add_row("3", "⚠️  Distraction Analysis")
            menu.add_row("4", "📊 Weekly Comparison")
            menu.add_row("5", "📅 Daily Productivity Breakdown")
            menu.add_row("b", "🔙 Back to Main Menu")
            
            self.console.print(Panel(menu, title="[bold]Insights Menu", border_style="cyan"))
            
            choice = Prompt.ask("\nSelect", default="1")
            
            if choice == "1":
                self._show_weekly_heatmap()
            elif choice == "2":
                self._show_peak_hours()
            elif choice == "3":
                self._show_distraction_analysis()
            elif choice == "4":
                self._show_weekly_comparison()
            elif choice == "5":
                self._show_daily_breakdown()
            elif choice == "b":
                break
    
    def _show_weekly_heatmap(self):
        """Display weekly productivity heatmap."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]🔥 Weekly Productivity Heatmap[/]\n")
        
        with self.console.status("[cyan]Generating heatmap..."):
            heatmap_str = self.heatmap_gen.generate_weekly_heatmap()
        
        # Display in a panel
        from rich.syntax import Syntax
        self.console.print(Panel(
            heatmap_str,
            title="[bold]Productivity Heatmap",
            border_style="cyan",
            padding=(1, 2)
        ))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def _show_peak_hours(self):
        """Display peak performance hours."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]🎯 Peak Performance Hours (Last 30 Days)[/]\n")
        
        with self.console.status("[cyan]Analyzing..."):
            peak_hours = self.productivity_analyzer.get_peak_hours(days=30)
        
        if not peak_hours:
            self.console.print("[yellow]Not enough data to determine peak hours yet.[/]\n")
        else:
            # Display peak hours
            peak_table = Table(box=box.ROUNDED, border_style="green")
            peak_table.add_column("Rank", style="bold yellow", justify="center")
            peak_table.add_column("Time Range", style="cyan")
            peak_table.add_column("Productivity Score", style="green", justify="right")
            peak_table.add_column("Rating", justify="center")
            
            for idx, (time_range, score) in enumerate(peak_hours, 1):
                # Rating based on score
                if score >= 80:
                    rating = "🔥🔥🔥"
                elif score >= 60:
                    rating = "🔥🔥"
                elif score >= 40:
                    rating = "🔥"
                else:
                    rating = "💤"
                
                peak_table.add_row(
                    f"#{idx}",
                    time_range,
                    f"{score:.1f}/100",
                    rating
                )
            
            self.console.print(Panel(
                peak_table,
                title="[bold green]Your Most Productive Times",
                border_style="green"
            ))
            
            # Recommendations
            if peak_hours:
                best_hour = peak_hours[0][0]
                self.console.print(f"\n[bold green]💡 Tip:[/] Schedule your most important tasks during {best_hour}")
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def _show_distraction_analysis(self):
        """Display distraction analysis."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]⚠️  Distraction Analysis[/]\n")
        
        # Get today's data
        today = datetime.now()
        start_of_day = today.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = today.replace(hour=23, minute=59, second=59).timestamp()
        
        with self.console.status("[cyan]Analyzing distractions..."):
            distraction_data = self.distraction_tracker.track_distractions(start_of_day, end_of_day)
            focus_breakdown = self.distraction_tracker.get_focus_vs_distracted_breakdown(start_of_day, end_of_day)
        
        # Summary stats
        summary_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        summary_table.add_column(style="bold white", width=25)
        summary_table.add_column(style="cyan", justify="right")
        
        summary_table.add_row("⏱️  Total Distraction Time", distraction_data['total_distraction_formatted'])
        summary_table.add_row("🔄 Context Switches", str(distraction_data['context_switches']))
        summary_table.add_row("✅ Focused Time", focus_breakdown['focused_formatted'])
        summary_table.add_row("📊 Focus Percentage", f"{focus_breakdown['focus_percentage']:.0f}%")
        
        self.console.print(Panel(summary_table, title="[bold yellow]⚠️  Summary", border_style="yellow"))
        
        # Category breakdown
        if distraction_data['by_category']:
            category_table = Table(box=box.SIMPLE, padding=(0, 2))
            category_table.add_column("Category", style="bold")
            category_table.add_column("Time", style="red", justify="right")
            
            for category, minutes in sorted(distraction_data['by_category'].items(), key=lambda x: x[1], reverse=True):
                emoji = {
                    'social_media': '📱',
                    'messaging': '💬',
                    'entertainment': '🎮',
                    'browsing': '🌐'
                }.get(category, '•')
                
                category_table.add_row(
                    f"{emoji} {category.replace('_', ' ').title()}",
                    f"{int(minutes)}m"
                )
            
            self.console.print(Panel(category_table, title="[bold red]📊 By Category", border_style="red"))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def _show_weekly_comparison(self):
        """Display weekly comparison."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]📊 Weekly Comparison[/]\n")
        
        # Get last two weeks
        this_week_start = (datetime.now() - timedelta(days=7)).timestamp()
        last_week_start = (datetime.now() - timedelta(days=14)).timestamp()
        
        with self.console.status("[cyan]Comparing weeks..."):
            comparison = self.productivity_analyzer.compare_weeks(last_week_start, this_week_start)
        
        # Display comparison
        comp_table = Table(box=box.ROUNDED, border_style="cyan")
        comp_table.add_column("Metric", style="bold white")
        comp_table.add_column("Last Week", style="yellow", justify="right")
        comp_table.add_column("This Week", style="cyan", justify="right")
        comp_table.add_column("Change", style="green", justify="right")
        
        def format_change(change):
            if change > 0:
                return f"[green]↑ {change:.0f}%[/green]"
            elif change < 0:
                return f"[red]↓ {abs(change):.0f}%[/red]"
            else:
                return "[dim]→ 0%[/dim]"
        
        comp_table.add_row(
            "Total Hours",
            f"{comparison['week1']['total_hours']:.1f}h",
            f"{comparison['week2']['total_hours']:.1f}h",
            format_change(comparison['changes']['time_change'])
        )
        
        comp_table.add_row(
            "Avg Productivity",
            f"{comparison['week1']['avg_productivity']:.1f}",
            f"{comparison['week2']['avg_productivity']:.1f}",
            format_change(comparison['changes']['productivity_change'])
        )
        
        comp_table.add_row(
            "Avg Focus Score",
            f"{comparison['week1']['avg_focus_score']:.1f}",
            f"{comparison['week2']['avg_focus_score']:.1f}",
            format_change(comparison['changes']['focus_change'])
        )
        
        self.console.print(Panel(comp_table, title="[bold]Week-over-Week Comparison", border_style="cyan"))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()
    
    def _show_daily_breakdown(self):
        """Display daily productivity breakdown."""
        self.console.clear()
        self.show_header()
        
        self.console.print("\n[bold cyan]📅 Daily Productivity Breakdown[/]\n")
        
        with self.console.status("[cyan]Generating breakdown..."):
            heatmap_str = self.heatmap_gen.generate_daily_heatmap()
        
        self.console.print(Panel(
            heatmap_str,
            title="[bold]Hourly Productivity",
            border_style="cyan",
            padding=(1, 2)
        ))
        
        self.console.print("\n[dim]Press Enter to continue...[/]")
        input()

    def run(self):
        """Run main TUI loop."""
        try:
            while self.running:
                self.console.clear()
                self.show_header()
                self.show_menu()
                
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
                elif choice == "6":
                    self.view_productivity_insights()
                elif choice.lower() in ['q', 'quit', 'exit']:
                    if Confirm.ask("\n[yellow]Are you sure you want to quit?[/]"):
                        self.running = False
        
        except KeyboardInterrupt:
            pass
        finally:
            self.console.print("\n[cyan]👋 Thank you for using KrypticTrack![/]\n")
            self.db.close()


def main():
    """Entry point."""
    app = KrypticTrackTUI()
    app.run()


if __name__ == "__main__":
    main()
    
