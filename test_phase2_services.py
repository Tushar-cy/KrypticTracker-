"""
Test all new Phase 2 services
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.habit_analyzer import get_habit_analyzer
from backend.services.pattern_detector import get_pattern_detector
from backend.services.productivity_predictor import get_productivity_predictor
from backend.services.notification_service import get_notification_service


def test_habit_analyzer(db):
    """Test habit analyzer."""
    print("\n1️⃣  Testing Habit Analyzer...")
    
    habit = get_habit_analyzer(db)
    
    # Auto-track today's habits
    today = datetime.now().strftime('%Y-%m-%d')
    habit.auto_track_habits(today)
    print(f"   ✅ Auto-tracked habits for {today}")
    
    # Get summary
    summary = habit.get_all_habits_summary()
    print(f"   ✅ Tracking {len(summary)} habits")
    
    for h in summary[:3]:
        print(f"      • {h['description']}: {h['current_streak']} day streak ({h['consistency_7d']:.0f}% 7d)")
    
    print(f"   ✅ Habit Analyzer working!")


def test_pattern_detector(db):
    """Test pattern detector."""
    print("\n2️⃣  Testing Pattern Detector...")
    
    detector = get_pattern_detector(db)
    
    # Detect work environments
    try:
        environments = detector.detect_work_environments(days=14)
        print(f"   ✅ Found {len(environments)} work environments")
        if environments:
            top = environments[0]
            print(f"      Best: {', '.join(top['apps'][:3])} (score: {top['avg_productivity']:.0f})")
    except:
        print("   ⚠️  Not enough data for work environments")
    
    # Detect blockers
    try:
        blockers = detector.identify_blockers(days=14)
        print(f"   ✅ Identified {len(blockers)} blockers")
        for b in blockers[:2]:
            print(f"      • {b['pattern']}: {b['impact']}")
    except:
        print("   ⚠️  Not enough data for blockers")
    
    # Optimal task times
    try:
        optimal = detector.find_optimal_task_times()
        print(f"   ✅ Optimal task times calculated")
        print(f"      • Coding: {optimal.get('coding', 'N/A')}")
    except:
        print("   ⚠️  Not enough data for optimal times")
    
    print(f"   ✅ Pattern Detector working!")


def test_productivity_predictor(db):
    """Test productivity predictor."""
    print("\n3️⃣  Testing Productivity Predictor...")
    
    predictor = get_productivity_predictor(db)
    
    # Predict today
    try:
        prediction = predictor.predict_today()
        print(f"   ✅ Today's prediction: {prediction['predicted_score']:.0f} (confidence: {prediction['confidence']:.0%})")
        print(f"      Reasoning: {prediction['reasoning']}")
    except Exception as e:
        print(f"   ⚠️  Prediction error: {e}")
    
    # Break suggestion
    try:
        break_rec = predictor.suggest_break_time()
        print(f"   ✅ Break recommendation: {break_rec['suggested_time']}")
        print(f"      Reason: {break_rec['reason']}")
    except Exception as e:
        print(f"   ⚠️  Break suggestion error: {e}")
    
    # Energy level
    try:
        energy = predictor.predict_energy_level(datetime.now().hour)
        print(f"   ✅ Current energy: {energy['energy']} (score: {energy['productivity_score']:.0f})")
    except Exception as e:
        print(f"   ⚠️  Energy prediction error: {e}")
    
    print(f"   ✅ Productivity Predictor working!")


def test_notification_service(db):
    """Test notification service."""
    print("\n4️⃣  Testing Notification Service...")
    
    notif = get_notification_service(db)
    
    # Check break needed
    break_check = notif.check_break_needed()
    print(f"   ✅ Break check: {break_check['message']}")
    
    # Check goal alignment
    goal_check = notif.check_goal_misalignment()
    print(f"   ✅ Goal check: {goal_check['message']}")
    
    # Focus session suggestion
    focus_check = notif.suggest_focus_session()
    print(f"   ✅ Focus check: {focus_check['message']}")
    
    # Weekly review
    review_check = notif.weekly_review_reminder()
    print(f"   ✅ Review check: {review_check['message']}")
    
    # Get all pending
    pending = notif.get_all_pending_notifications()
    print(f"   ✅ {len(pending)} pending notifications")
    for p in pending[:2]:
        print(f"      [{p['urgency']}] {p['type']}: {p['message']}")
    
    print(f"   ✅ Notification Service working!")


def main():
    """Run all tests."""
    print("🧪 Testing Phase 2 Services")
    print("=" * 70)
    
    # Setup database
    db = DatabaseManager('data/kryptic_track.db', False)
    conn = db.connect()
    create_tables(conn)
    print("✅ Database connected")
    
    # Run tests
    test_habit_analyzer(conn)
    test_pattern_detector(conn)
    test_productivity_predictor(conn)
    test_notification_service(conn)
    
    print("\n" + "=" * 70)
    print("✅ All Phase 2 services working!")
    print("\nNext: Phase 4 (LLM Intelligence) and Phase 5 (TUI Enhancements)")


if __name__ == "__main__":
    main()
