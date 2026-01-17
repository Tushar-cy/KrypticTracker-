"""
API endpoint for viewing logs in a GUI-friendly way
"""

from flask import Blueprint, jsonify, current_app, request

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/logs', methods=['GET'])
def get_logs():
    """Get recent logs for GUI display."""
    try:
        logger = current_app.config.get('logger')
        if not logger:
            return jsonify({'logs': [], 'error': 'Logger not configured'}), 200
        
        level = request.args.get('level')  # error, warning, info, all
        limit = request.args.get('limit', 50, type=int)
        
        logs = logger.get_recent_logs(level=level if level != 'all' else None, limit=limit)
        stats = logger.get_stats()
        
        return jsonify({
            'logs': logs,
            'stats': stats
        }), 200
        
    except Exception as e:
        return jsonify({'logs': [], 'error': str(e)}), 200

