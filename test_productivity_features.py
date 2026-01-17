#!/usr/bin/env python3
"""
Test Advanced Productivity Features

Tests the new productivity pattern analyzer, distraction tracker,
and heatmap generator services.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from backend.services.productivity_patterns import get_productivity_pattern_analyzer
from backend.services.distraction_tracker import get_distraction_tracker
from backend.services.heatmap_generator import get_heatmap_generator

def test_productivity_features():
    """Test all new productivity features."""
    print("🧪 Testing Advanced Productivity Features\n")
    print("=" * 70)
    
    # Initialize
    db = DatabaseManager(db_path='data/kryptic_track.db', encrypted=False)
    conn = db.connect()
    create_tables(conn)
    print("✅ Database connected\n")
    
    # Test 1: Productivity Pattern Analyzer
    print("1️⃣  Testing Productivity Pattern Analyzer...")
    try:
        analyzer = get_productivity_pattern_analyzer(conn)
        
        # Get peak hours
        peak_hours = analyzer.get_peak_hours(days=30)
        print(f"   ✅ Peak hours detected: {len(peak_hours)}")
        if peak_hours:
            for idx, (time_range, score) in enumerate(peak_hours, 1):
                print(f"      #{idx}: {time_range} (score: {score:.1f})")
        
        # Get hourly productivity
        end_time = datetime.now().timestamp()
        start_time = (datetime.now() - timedelta(days=1)).timestamp()
        hourly_scores = analyzer.analyze_hourly_productivity(start_time, end_time)
        active_hours = [h for h, s in hourly_scores.items() if s > 0]
        print(f"   ✅ Hourly analysis: {len(active_hours)} active hours")
        
        # Weekly comparison
        this_week = (datetime.now() - timedelta(days=7)).timestamp()
        last_week = (datetime.now() - timedelta(days=14)).timestamp()
        comparison = analyzer.compare_weeks(last_week, this_week)
        print(f"   ✅ Weekly comparison: {comparison['changes']['productivity_change']:+.1f}% productivity change")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 2: Distraction Tracker
    print("\n2️⃣  Testing Distraction Tracker...")
    try:
        tracker = get_distraction_tracker(conn)
        
        # Get today's distractions
        today = datetime.now()
        start_of_day = today.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = today.replace(hour=23, minute=59, second=59).timestamp()
        
        distractions = tracker.track_distractions(start_of_day, end_of_day)
        print(f"   ✅ Distraction time: {distractions['total_distraction_formatted']}")
        print(f"   ✅ Context switches: {distractions['context_switches']}")
        print(f"   ✅ Categories tracked: {len(distractions['by_category'])}")
        
        # Focus breakdown
        focus_breakdown = tracker.get_focus_vs_distracted_breakdown(start_of_day, end_of_day)
        print(f"   ✅ Focus percentage: {focus_breakdown['focus_percentage']:.0f}%")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 3: Heatmap Generator
    print("\n3️⃣  Testing Heatmap Generator...")
    try:
        heatmap_gen = get_heatmap_generator(conn)
        
        # Weekly heatmap
        weekly_heatmap = heatmap_gen.generate_weekly_heatmap()
        print(f"   ✅ Weekly heatmap: {len(weekly_heatmap.split(chr(10)))} lines")
        
        # Daily heatmap
        daily_heatmap = heatmap_gen.generate_daily_heatmap()
        print(f"   ✅ Daily heatmap: {len(daily_heatmap.split(chr(10)))} lines")
        
        # Comparison heatmap
        comparison_heatmap = heatmap_gen.generate_comparison_heatmap(weeks_back=4)
        print(f"   ✅ Comparison heatmap: 4 weeks analyzed")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 70)
    print("✅ All advanced productivity features working!\n")
    
    # Show sample output
    print("\n📊 Sample Weekly Heatmap:")
    print("-" * 70)
    print(weekly_heatmap[:500] + "..." if len(weekly_heatmap) > 500 else weekly_heatmap)
    print("-" * 70)
    
    return True

if __name__ == "__main__":
    success = test_productivity_features()
    sys.exit(0 if success else 1)
