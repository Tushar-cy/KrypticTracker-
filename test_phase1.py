"""Test backend services"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.session_detector import get_session_detector
from backend.services.time_tracker import get_time_tracker
from backend.services.goal_service import get_goal_service

print("🔧 Initializing database...")
db = DatabaseManager(db_path='data/kr yptic_track.db', encrypted=False)
conn = db.connect()

print("📊 Creating/updating database tables...")
create_tables(conn)

print("\n✅ Phase 1 Backend Services Test")
print("=" * 50)

print("\n1. Session Detector")
detector = get_session_detector(conn)
print("   ✓ Session detector initialized")

print("\n2. Time Tracker")
tracker = get_time_tracker(conn)
print("   ✓ Time tracker initialized")

print("\n3. Goal Service")
goal_service = get_goal_service(conn)
print("   ✓ Goal service initialized")

# Test creating a goal
print("\n4. Testing Goal Creation")
goal_id = goal_service.create_goal(
    goal_text="Master Python backend development",
    keywords=["python", "flask", "backend", "api"],
    category="learning"
)
print(f"   ✓ Created goal with ID: {goal_id}")

# Test getting active goals
goals = goal_service.get_active_goals()
print(f"   ✓ Retrieved {len(goals)} active goal(s)")

if goals:
    for goal in goals:
        print(f"      - {goal['goal_text']}")
        print(f"        Keywords: {', '.join(goal['keywords'])}")

print("\n" + "=" * 50)
print("✅ All Phase 1 services working correctly!")
print("\nReady for Phase 2: LLM Intelligence Layer")
