#!/usr/bin/env python3
"""
Comprehensive TUI Testing Script
Tests all major features to ensure everything works
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.session_detector import get_session_detector
from backend.services.time_tracker import get_time_tracker
from backend.services.goal_service import get_goal_service
from backend.services.daily_summary import get_daily_summary_generator
from backend.services.llm_service import get_llm_service
from datetime import datetime

def test_all_features():
    """Test all backend features."""
    print("🧪 Comprehensive Backend Testing\n")
    print("=" * 60)
    
    # Initialize
    db = DatabaseManager(db_path='data/kryptic_track.db', encrypted=False)
    conn = db.connect()
    create_tables(conn)
    print("✅ Database initialized\n")
    
    # Test 1: Session Detector
    print("1️⃣  Testing Session Detector...")
    try:
        detector = get_session_detector(conn)
        sessions = detector.detect_sessions()
        print(f"   ✅ Found {len(sessions)} sessions")
        if sessions:
            print(f"   └─ Sample: {sessions[0]['session_type']} ({sessions[0]['duration_minutes']}m)")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 2: Time Tracker
    print("\n2️⃣  Testing Time Tracker...")
    try:
        tracker = get_time_tracker(conn)
        today = datetime.now().strftime('%Y-%m-%d')
        breakdown = tracker.get_daily_breakdown(today)
        print(f"   ✅ Total time: {breakdown['total_time'].get('formatted', '0m')}")
        print(f"   └─ Apps tracked: {len(breakdown['by_app'])}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 3: Goal Service
    print("\n3️⃣  Testing Goal Service...")
    try:
        goal_service = get_goal_service(conn)
        goals = goal_service.get_active_goals()
        print(f"   ✅ Active goals: {len(goals)}")
        if goals:
            print(f"   └─ Sample: {goals[0]['goal_text']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 4: Daily Summary
    print("\n4️⃣  Testing Daily Summary Generator...")
    try:
        summary_gen = get_daily_summary_generator(conn)
        today = datetime.now().strftime('%Y-%m-%d')
        summary = summary_gen.generate_summary(today, use_llm=False)
        print(f"   ✅ Summary generated")
        print(f"   └─ Sessions: {summary['sessions']['count']}")
        print(f"   └─ Focus score: {summary['productivity']['focus_score']:.1f}/100")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Test 5: LLM Service
    print("\n5️⃣  Testing LLM Service...")
    try:
        llm = get_llm_service()
        available = llm.is_available()
        print(f"   {'✅' if available else '⚠️ '} LM Studio: {'Online' if available else 'Offline'}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    return True

if __name__ == "__main__":
    success = test_all_features()
    sys.exit(0 if success else 1)
