"""
Quick test for daily summary with LM Studio
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.daily_summary import get_daily_summary_generator
from backend.services.llm_service import get_llm_service

print("🧠 Testing Daily Summary Generator with Qwen 3-1.7B\n")
print("=" * 60)

# Initialize
db = DatabaseManager(db_path='data/kryptic_track.db', encrypted=False)
conn = db.connect()
create_tables(conn)  # Ensure all tables exist

# Check LLM availability
llm = get_llm_service()
print("\n1. Checking LM Studio connection...")
if llm.is_available():
    print("   ✅ LM Studio is running on http://127.0.0.1:1234")
else:
    print("   ❌ LM Studio not available. Summary will use fallback narrative.")

# Generate summary for today
print("\n2. Generating daily summary for today...")
generator = get_daily_summary_generator(conn)
today = datetime.now().strftime('%Y-%m-%d')

try:
    summary = generator.generate_summary(today, use_llm=True)
    
    print(f"\n{'='*60}")
    print(f"📅 Daily Summary for {summary['date']}")
    print(f"{'='*60}\n")
    
    # Print structured data
    print(f"⏱️  Total Time: {summary['total_time'].get('formatted', 'N/A')}")
    print(f"📊 Sessions: {summary['sessions']['count']}")
    print(f"🎯 Focus Score: {summary['productivity']['focus_score']}/100")
    print(f"🔄 Context Switches: {summary['productivity']['context_switches']}")
    
    if summary['sessions']['top_projects']:
        print("\n🚀 Top Projects:")
        for proj in summary['sessions']['top_projects'][:3]:
            print(f"   - {proj['project']}: {proj['hours']}h")
    
    if summary['time_breakdown']['by_app']:
        print("\n💻 Top Apps:")
        for app in summary['time_breakdown']['by_app'][:3]:
            print(f"   - {app['app']}: {app.get('formatted', str(app['hours']) + 'h')}")
    
    print(f"\n📈 Statistics:")
    print(f"   - Git commits: {summary['statistics'].get('git_commits', 0)}")
    print(f"   - Terminal commands: {summary['statistics'].get('terminal_commands', 0)}")
    print(f"   - Total actions: {summary['statistics'].get('total_actions', 0)}")
    
    if summary.get('goals'):
        print("\n🎯 Goal Alignment:")
        for goal_info in summary['goals']:
            print(f"   {goal_info['feedback']}")
    
    # Print LLM narrative
    print(f"\n{'='*60}")
    print("🤖 LLM Narrative Summary:")
    print(f"{'='*60}\n")
    print(summary.get('narrative', 'No narrative generated'))
    
    print(f"\n{'='*60}")
    print("✅ Daily summary generated successfully!")
    print(f"{'='*60}\n")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
