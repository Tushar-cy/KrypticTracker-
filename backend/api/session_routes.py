"""
Session and Time Tracking API Routes
"""

from flask import Blueprint, request, jsonify
from database import DatabaseManager
from backend.services.session_detector import get_session_detector
from backend.services.time_tracker import get_time_tracker
from backend.services.goal_service import get_goal_service
from datetime import datetime, timedelta
import time

sessions_bp = Blueprint('sessions', __name__)


@sessions_bp.route('/api/sessions/detect', methods=['POST'])
def detect_sessions():
    """Detect sessions for a given time range."""
    try:
        data = request.get_json() or {}
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        
        db = get_db_connection()
        detector = get_session_detector(db)
        
        sessions = detector.detect_sessions(start_time, end_time)
        
        return jsonify({
            'success': True,
            'sessions': sessions,
            'count': len(sessions)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/sessions/today', methods=['GET'])
def get_today_sessions():
    """Get all sessions for today."""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        db = get_db_connection()
        detector = get_session_detector(db)
        
        sessions = detector.get_sessions_for_day(today)
        
        return jsonify({
            'success': True,
            'date': today,
            'sessions': sessions,
            'count': len(sessions)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/time/daily', methods=['GET'])
def get_daily_breakdown():
    """Get time breakdown for a specific date."""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        db = get_db_connection()
        tracker = get_time_tracker(db)
        
        breakdown = tracker.get_daily_breakdown(date)
        
        return jsonify({
            'success': True,
            'breakdown': breakdown
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/time/by-app', methods=['GET'])
def get_time_by_app():
    """Get time spent by application."""
    try:
        # Get time range from query params (default: today)
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        dt = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        db = get_db_connection()
        tracker = get_time_tracker(db)
        
        app_times = tracker.time_by_app(start_of_day, end_of_day)
        
        return jsonify({
            'success': True,
            'date': date,
            'apps': app_times
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/time/by-project', methods=['GET'])
def get_time_by_project():
    """Get time spent by project."""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        dt = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = dt.replace(hour=0, minute=0, second=0).timestamp()
        end_of_day = dt.replace(hour=23, minute=59, second=59).timestamp()
        
        db = get_db_connection()
        tracker = get_time_tracker(db)
        
        project_times = tracker.time_by_project(start_of_day, end_of_day)
        
        return jsonify({
            'success': True,
            'date': date,
            'projects': project_times
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/goals', methods=['GET'])
def get_goals():
    """Get all active goals."""
    try:
        db = get_db_connection()
        goal_service = get_goal_service(db)
        
        goals = goal_service.get_active_goals()
        
        return jsonify({
            'success': True,
            'goals': goals
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/goals', methods=['POST'])
def create_goal():
    """Create a new goal."""
    try:
        data = request.get_json()
        
        goal_text = data.get('goal_text')
        keywords = data.get('keywords', [])
        target_date = data.get('target_date')
        category = data.get('category', 'general')
        
        if not goal_text:
            return jsonify({'error': 'goal_text is required'}), 400
        
        db = get_db_connection()
        goal_service = get_goal_service(db)
        
        goal_id = goal_service.create_goal(goal_text, keywords, target_date, category)
        
        return jsonify({
            'success': True,
            'goal_id': goal_id
        }), 201
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/goals/<int:goal_id>/alignment', methods=['GET'])
def check_goal_alignment(goal_id):
    """Check alignment for a specific goal."""
    try:
        timeframe = request.args.get('timeframe', 'week')
        
        # Calculate time range
        now = time.time()
        if timeframe == 'day':
            start_time = now - (24 * 3600)
        elif timeframe == 'week':
            start_time = now - (7 * 24 * 3600)
        else:  # month
            start_time = now - (30 * 24 * 3600)
        
        db = get_db_connection()
        goal_service = get_goal_service(db)
        
        alignment = goal_service.check_alignment(goal_id, start_time, now)
        feedback = goal_service.generate_feedback(goal_id, timeframe)
        
        return jsonify({
            'success': True,
            'alignment': alignment,
            'feedback': feedback
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/goals/<int:goal_id>/progress', methods=['GET'])
def get_goal_progress(goal_id):
    """Get goal progress history."""
    try:
        days = request.args.get('days', 7, type=int)
        
        db = get_db_connection()
        goal_service = get_goal_service(db)
        
        history = goal_service.get_goal_progress_history(goal_id, days)
        
        return jsonify({
            'success': True,
            'goal_id': goal_id,
            'history': history
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/api/goals/<int:goal_id>', methods=['PUT'])
def update_goal(goal_id):
    """Update goal status."""
    try:
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['active', 'completed', 'abandoned']:
            return jsonify({'error': 'Invalid status'}), 400
        
        db = get_db_connection()
        goal_service = get_goal_service(db)
        
        goal_service.update_goal_status(goal_id, status)
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
