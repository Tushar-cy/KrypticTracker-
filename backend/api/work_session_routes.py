"""API routes for work session management."""

from flask import Blueprint, request, jsonify, current_app
from backend.services.work_session_service import WorkSessionService
from backend.utils.exceptions import DatabaseError, ValidationError
from backend.utils.logger import get_logger
from backend.api.decorators import handle_errors

logger = get_logger("work_session_api")

work_session_bp = Blueprint('work_session', __name__)


@work_session_bp.route('/start', methods=['POST'])
@handle_errors
def start_work_session():
    """Start a new work session for today."""
    try:
        data = request.get_json() or {}
        planned_work = data.get('planned_work', '')
        
        if not planned_work or len(planned_work.strip()) < 3:
            raise ValidationError(
                message="planned_work is required and must be at least 3 characters",
                error_code="VALIDATION_ERROR"
            )
        
        db = current_app.config.get('db')
        if not db:
            return jsonify({'error': 'Database not configured'}), 500
        
        conn = db.connect()
        service = WorkSessionService(conn)
        
        session = service.start_work_session(planned_work.strip())
        
        logger.info("Work session started via API", session_id=session['session_id'])
        
        return jsonify({
            'success': True,
            'session': session
        }), 201
        
    except ValidationError as e:
        return jsonify({
            'error': e.message,
            'error_code': e.error_code
        }), 400
    except DatabaseError as e:
        return jsonify({
            'error': str(e),
            'error_code': 'DATABASE_ERROR'
        }), 500


@work_session_bp.route('/end', methods=['POST'])
@handle_errors
def end_work_session():
    """End today's work session and get analysis."""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        
        db = current_app.config.get('db')
        if not db:
            return jsonify({'error': 'Database not configured'}), 500
        
        conn = db.connect()
        service = WorkSessionService(conn)
        
        result = service.end_work_session(session_id)
        
        logger.info("Work session ended via API", session_id=result['session_id'])
        
        return jsonify({
            'success': True,
            'session': result
        }), 200
        
    except DatabaseError as e:
        return jsonify({
            'error': str(e),
            'error_code': 'DATABASE_ERROR'
        }), 500


@work_session_bp.route('/today', methods=['GET'])
@handle_errors
def get_today_session():
    """Get today's work session."""
    try:
        db = current_app.config.get('db')
        if not db:
            return jsonify({'error': 'Database not configured'}), 500
        
        conn = db.connect()
        service = WorkSessionService(conn)
        
        session = service.get_today_session()
        
        if not session:
            return jsonify({
                'success': True,
                'session': None,
                'message': 'No work session found for today'
            }), 200
        
        return jsonify({
            'success': True,
            'session': session
        }), 200
        
    except Exception as e:
        logger.error("Failed to get today's session", error=str(e))
        return jsonify({
            'error': str(e),
            'error_code': 'INTERNAL_ERROR'
        }), 500


@work_session_bp.route('/history', methods=['GET'])
@handle_errors
def get_session_history():
    """Get work session history."""
    try:
        limit = request.args.get('limit', 30, type=int)
        
        db = current_app.config.get('db')
        if not db:
            return jsonify({'error': 'Database not configured'}), 500
        
        conn = db.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, date, start_time, end_time, planned_work,
                actual_summary, time_wasted_minutes, idle_time_minutes,
                focused_time_minutes, insights
            FROM work_sessions
            ORDER BY date DESC, start_time DESC
            LIMIT ?
        """, (limit,))
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'session_id': row[0],
                'date': row[1],
                'start_time': row[2],
                'end_time': row[3],
                'planned_work': row[4],
                'actual_summary': row[5],
                'time_wasted_minutes': row[6],
                'idle_time_minutes': row[7],
                'focused_time_minutes': row[8],
                'insights': row[9]
            })
        
        return jsonify({
            'success': True,
            'sessions': sessions,
            'count': len(sessions)
        }), 200
        
    except Exception as e:
        logger.error("Failed to get session history", error=str(e))
        return jsonify({
            'error': str(e),
            'error_code': 'INTERNAL_ERROR'
        }), 500

