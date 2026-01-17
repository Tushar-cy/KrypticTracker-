"""
API Routes for Frontend Integration
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from database import DatabaseManager

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Initialize database
db = DatabaseManager('data/kryptic_track.db', False)
conn = db.connect()

@api_bp.route('/log-action', methods=['POST'])
def log_action():
    """Log a user action."""
    try:
        from flask import request
        import json
        import time
        
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO actions (timestamp, source, action_type, context_json)
            VALUES (?, ?, ?, ?)
        """, (
            time.time(),
            data.get('source', 'web'),
            data.get('action_type', 'unknown'),
            json.dumps(data.get('context', {}))
        ))
        conn.commit()
        
        return jsonify({'status': 'success'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stats/quick', methods=['GET'])
def get_quick_stats():
    """Get quick stats for dashboard (optimized)."""
    try:
        from backend.services.distraction_tracker import get_distraction_tracker
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        from backend.services.goal_service import get_goal_service
        
        today = datetime.now()
        
        # Quick defaults in case of errors
        result = {
            'focusPercentage': 0,
            'contextSwitches': 0,
            'focusedTime': '0m',
            'activeGoals': 0,
            'peakHour': 'N/A',
            'currentDay': today.strftime('%A, %B %d')
        }
        
        try:
            # Get services
            dist = get_distraction_tracker(conn)
            prod = get_productivity_pattern_analyzer(conn)
            goals_svc = get_goal_service(conn)
            
            start = today.replace(hour=0, minute=0, second=0).timestamp()
            now = today.timestamp()
            
            # Get data with timeouts/fallbacks
            try:
                focus_data = dist.get_focus_vs_distracted_breakdown(start, now)
                result['focusPercentage'] = focus_data.get('focus_percentage', 0)
                result['focusedTime'] = focus_data.get('focused_formatted', '0m')
            except:
                pass
            
            try:
                dist_data = dist.track_distractions(start, now)
                result['contextSwitches'] = dist_data.get('context_switches', 0)
            except:
                pass
            
            try:
                peaks = prod.get_peak_hours(days=7)
                result['peakHour'] = peaks[0][0] if peaks else 'N/A'
            except:
                pass
            
            try:
                active_goals = goals_svc.get_active_goals()
                result['activeGoals'] = len(active_goals)
            except:
                pass
                
        except Exception as e:
            # Log error but return defaults
            print(f"Error in stats/quick: {e}")
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stats/activity', methods=['GET'])
def get_activity():
    """Get 24-hour activity chart data."""
    try:
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        
        prod = get_productivity_pattern_analyzer(conn)
        
        today = datetime.now()
        start = today.replace(hour=0, minute=0, second=0).timestamp()
        now = today.timestamp()
        
        hourly = prod.analyze_hourly_productivity(start, now)
        
        # Format for chart
        data = [
            {'hour': hour, 'productivity': score}
            for hour, score in hourly.items()
        ]
        
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stats/heatmap', methods=['GET'])
def get_heatmap():
    """Get productivity heatmap data."""
    try:
        from backend.services.productivity_patterns import get_productivity_pattern_analyzer
        from flask import request
        
        days = int(request.args.get('days', 7))
        prod = get_productivity_pattern_analyzer(conn)
        
        heatmap = prod.generate_heatmap_data(days=days)
        
        return jsonify(heatmap)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sessions', methods=['POST'])
def create_session():
    """Manually log a work session."""
    try:
        from backend.services.session_detector import get_session_detector
        from flask import request
        
        data = request.json
        if not data or 'project' not in data or 'duration' not in data:
            return jsonify({'error': 'Missing project or duration'}), 400
            
        sess = get_session_detector(conn)
        
        session_id = sess.create_session(
            project=data['project'],
            session_type=data.get('session_type', 'coding'),
            duration_minutes=int(data['duration']),
            start_time=data.get('start_time')
        )
        
        return jsonify({'id': session_id, 'message': 'Session logged successfully'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sessions', methods=['GET'])
def get_sessions():
    """Get work sessions."""
    try:
        from backend.services.session_detector import get_session_detector
        
        sess = get_session_detector(conn)
        
        # Get date range from query params
        today = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        sessions = sess.get_session_summary_by_day(week_ago, today)
        
        return jsonify(sessions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/habits', methods=['GET'])
def get_habits():
    """Get habit tracking data."""
    try:
        from backend.services.habit_analyzer import get_habit_analyzer
        
        habits_svc = get_habit_analyzer(conn)
        summary = habits_svc.get_all_habits_summary()
        
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/habits', methods=['POST'])
def create_habit():
    """Create a new habit."""
    try:
        from backend.services.habit_analyzer import get_habit_analyzer
        from flask import request
        
        data = request.json
        if not data or 'name' not in data or 'description' not in data:
            return jsonify({'error': 'Missing name or description'}), 400
            
        habits_svc = get_habit_analyzer(conn)
        
        habits_svc.create_habit(
            name=data['name'],
            description=data['description'],
            target_value=data.get('target_value', 1),
            unit=data.get('unit', 'count'),
            keywords=data.get('keywords', [])
        )
        
        return jsonify({'message': 'Habit created successfully'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/goals', methods=['GET'])
def get_goals():
    """Get active goals."""
    try:
        from backend.services.goal_service import get_goal_service
        
        goals_svc = get_goal_service(conn)
        goals = goals_svc.get_active_goals()
        
        # Add progress and alignment (mocked for now)
        for goal in goals:
            goal['progress'] = 50  # TODO: Calculate actual progress
            goal['alignmentPercentage'] = 65  # TODO: Calculate from alignment
        
        return jsonify(goals)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/goals', methods=['POST'])
def create_goal():
    """Create a new goal."""
    try:
        from backend.services.goal_service import get_goal_service
        from flask import request
        
        data = request.json
        if not data or 'goal_text' not in data:
            return jsonify({'error': 'Missing goal_text'}), 400
            
        goals_svc = get_goal_service(conn)
        
        # Parse target date if provided
        target_date = None
        if 'target_date' in data and data['target_date']:
            try:
                dt = datetime.strptime(data['target_date'], '%Y-%m-%d')
                target_date = dt.timestamp()
            except ValueError:
                pass
        
        goal_id = goals_svc.create_goal(
            goal_text=data['goal_text'],
            keywords=data.get('keywords', []),
            target_date=target_date,
            category=data.get('category', 'general')
        )
        
        return jsonify({'id': goal_id, 'message': 'Goal created successfully'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/insights/predictions', methods=['GET'])
def get_predictions():
    """Get productivity predictions."""
    try:
        from backend.services.productivity_predictor import get_productivity_predictor
        
        predictor = get_productivity_predictor(conn)
        prediction = predictor.predict_today()
        
        return jsonify(prediction)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/insights/patterns', methods=['GET'])
def get_patterns():
    """Get productive work patterns."""
    try:
        from backend.services.pattern_detector import get_pattern_detector
        
        patterns_svc = get_pattern_detector(conn)
        patterns = patterns_svc.detect_work_environments(days=14)
        
        return jsonify(patterns if patterns else [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/insights/blockers', methods=['GET'])
def get_blockers():
    """Get productivity blockers."""
    try:
        from backend.services.pattern_detector import get_pattern_detector
        
        patterns_svc = get_pattern_detector(conn)
        blockers = patterns_svc.identify_blockers(days=14)
        
        return jsonify(blockers if blockers else [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """Get pending notifications."""
    try:
        from backend.services.notification_service import get_notification_service
        
        notif = get_notification_service(conn)
        notifications = notif.get_all_pending_notifications()
        
        return jsonify(notifications)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})
