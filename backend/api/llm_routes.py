"""
LLM API Routes for Chat and Suggestions
"""

from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from backend.services.llm_service import get_llm_service

llm_bp = Blueprint('llm', __name__)

# Rate limiter will be accessed from app config


@llm_bp.route('/chat', methods=['POST'])
def chat():
    """Chat with LLM about user behavior."""
    try:
        data = request.get_json()
        message = data.get('message', '')
        intent = data.get('intent')
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        llm = get_llm_service()
        
        # Check if LLM is available first
        if not llm.is_available():
            return jsonify({
                'error': 'LLM service not available. Please start LM Studio and ensure a model is loaded.',
                'response': None
            }), 200
        
        # Load user context if available
        db = current_app.config.get('db')
        search_results = data.get('search_results', [])
        
        if db:
            try:
                conn = db.connect()
                llm.load_user_context(conn)
            except Exception as e:
                # Log but continue - context loading is optional
                logger = current_app.config.get('logger')
                if logger:
                    logger.log_action('warning', 'Failed to load user context for LLM', error=str(e))
        
        try:
            response = llm.chat(message, intent=intent, search_results=search_results)
            
            # Response should be a valid string at this point (exceptions are raised, not returned)
            if not response or not isinstance(response, str):
                raise Exception("Invalid response from LLM")
            
            return jsonify({
                'response': response,
                'model': llm.model
            }), 200
            
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error messages
            if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                error_msg = "Request timed out. The model is taking too long to respond. Try using a lighter/faster model or wait a bit longer."
            elif 'connection' in error_msg.lower() or 'connect' in error_msg.lower() or 'LM Studio' in error_msg:
                error_msg = "Cannot connect to LM Studio. Make sure LM Studio is running on http://localhost:1234 and a model is loaded."
            elif 'not available' in error_msg.lower():
                error_msg = "LLM service not available. Please start LM Studio and ensure a model is loaded."
            
            return jsonify({
                'error': error_msg,
                'response': None
            }), 200
        
    except Exception as e:
        return jsonify({
            'error': f'Server error: {str(e)}',
            'response': None
        }), 500


@llm_bp.route('/suggestions', methods=['GET'])
def get_suggestions():
    """Get AI-generated suggestions based on behavior."""
    try:
        llm = get_llm_service()
        
        if not llm.is_available():
            return jsonify({
                'suggestions': [],
                'error': 'LLM service not available. Start LM Studio and load a model.'
            }), 200
        
        # Get recent behavior data
        db = current_app.config.get('db')
        if not db:
            return jsonify({'suggestions': []}), 200
        
        conn = db.connect()
        cursor = conn.cursor()
        
        # Get behavior summary
        cursor.execute("""
            SELECT 
                source,
                COUNT(*) as count,
                MAX(timestamp) as last_action
            FROM actions
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY source
            ORDER BY count DESC
        """)
        
        behavior_data = {
            'sources': [{'source': r[0], 'count': r[1], 'last_action': r[2]} for r in cursor.fetchall()]
        }
        
        suggestion = llm.generate_suggestion(behavior_data)
        
        return jsonify({
            'suggestions': [suggestion] if suggestion else [],
            'model': llm.model
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e), 'suggestions': []}), 200


@llm_bp.route('/analyze', methods=['POST'])
def analyze_behavior():
    """Analyze behavior insights using LLM."""
    try:
        data = request.get_json()
        insights = data.get('insights', [])
        
        if not insights:
            return jsonify({'error': 'Insights are required'}), 400
        
        llm = get_llm_service()
        analysis = llm.analyze_behavior(insights)
        
        return jsonify({
            'analysis': analysis,
            'model': llm.model
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@llm_bp.route('/surprised-me', methods=['GET'])
def get_surprised_me():
    """Generate a surprising insight about user behavior."""
    try:
        llm = get_llm_service()
        
        if not llm.is_available():
            return jsonify({
                'insight': None,
                'error': 'LLM service not available. Start LM Studio and load a model.'
            }), 200
        
        # Get behavior data
        db = current_app.config.get('db')
        if not db:
            return jsonify({'insight': None, 'error': 'Database not available'}), 200
        
        conn = db.connect()
        cursor = conn.cursor()
        
        # Get comprehensive behavior data
        cursor.execute("""
            SELECT 
                source,
                action_type,
                COUNT(*) as count,
                strftime('%H', datetime(timestamp, 'unixepoch')) as hour,
                strftime('%w', datetime(timestamp, 'unixepoch')) as day_of_week
            FROM actions
            WHERE timestamp > datetime('now', '-30 days')
            GROUP BY source, action_type, hour, day_of_week
            ORDER BY count DESC
        """)
        
        behavior_data = {
            'actions': [{
                'source': r[0],
                'action_type': r[1],
                'count': r[2],
                'hour': r[3],
                'day_of_week': r[4]
            } for r in cursor.fetchall()],
            'total_actions': sum(r[2] for r in cursor.fetchall() if r[2])
        }
        
        # Get time-based patterns
        cursor.execute("""
            SELECT 
                strftime('%H', datetime(timestamp, 'unixepoch')) as hour,
                COUNT(*) as count
            FROM actions
            WHERE timestamp > datetime('now', '-30 days')
            GROUP BY hour
            ORDER BY count DESC
        """)
        
        behavior_data['peak_hours'] = [{'hour': r[0], 'count': r[1]} for r in cursor.fetchall()]
        
        insight = llm.generate_surprised_me_insight(behavior_data)
        
        return jsonify({
            'insight': insight,
            'model': llm.model
        }), 200
        
    except Exception as e:
        return jsonify({'insight': None, 'error': str(e)}), 200


@llm_bp.route('/status', methods=['GET'])
def llm_status():
    """Check LLM service status."""
    try:
        llm = get_llm_service()
        is_available = llm.is_available()
        
        return jsonify({
            'available': is_available,
            'model': llm.model,
            'base_url': llm.base_url
        }), 200
        
    except Exception as e:
        return jsonify({
            'available': False,
            'error': str(e)
        }), 200

