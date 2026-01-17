"""Flask backend server for KrypticTrack."""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
import json
from pathlib import Path
import sys
import os

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from utils.helpers import load_config, generate_session_id
from backend.utils.logger import setup_logging, get_logger
from backend.api.routes import api_bp
from backend.api.llm_routes import llm_bp
from backend.api.work_session_routes import work_session_bp
from backend.services.data_cleaner import create_cleanup_endpoint

# Frontend build directory (Vite output)
static_root = project_root / 'dashboard' / 'web' / 'static'
spa_dist_dir = static_root / 'dist'

if not spa_dist_dir.exists():
    print(f"⚠️  Frontend build not found at {spa_dist_dir}. Run `npm run build` inside /frontend.")

app = Flask(__name__)
CORS(app)  # Enable CORS for extensions

# Load configuration
config = load_config()
db_config = config['database']
backend_config = config.get('backend', {})

# Setup structured logging
log_level = backend_config.get('log_level', 'INFO')
log_file = backend_config.get('log_file', 'logs/backend.log')
setup_logging(log_level=log_level, log_file=log_file)
logger = get_logger("app")

# Setup rate limiting (increased for extension popup auto-refresh)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["5000 per day", "1000 per hour"],  # Extension refreshes every 5s = ~720/hour
    storage_uri="memory://",  # Use in-memory storage (can switch to Redis in production)
)

# Store limiter in app config for use in blueprints
app.config['limiter'] = limiter

# Initialize database
db = DatabaseManager(
    db_path=db_config['path'],
    encrypted=db_config['encrypted']
)
db.connect()
create_tables(db.connection)

# Current session - create in database
current_session_id = generate_session_id()
session_start_time = time.time()

# Create session record in database
conn = db.connect()
cursor = conn.cursor()
cursor.execute("""
    INSERT OR IGNORE INTO sessions (id, start_time, total_actions, sources_used, context_summary)
    VALUES (?, ?, 0, ?, ?)
""", (current_session_id, session_start_time, json.dumps([]), json.dumps({})))
conn.commit()

# Register blueprints
app.register_blueprint(api_bp)  # Already has /api prefix
app.register_blueprint(llm_bp, url_prefix='/api/llm')
app.register_blueprint(work_session_bp, url_prefix='/api/work-session')
cleanup_bp = create_cleanup_endpoint()
app.register_blueprint(cleanup_bp, url_prefix='/api')

# Rate limiting is applied directly above

# Store db in app context for routes
app.config['db'] = db
app.config['current_session_id'] = current_session_id
app.config['config'] = config

# Initialize model manager
from backend.services.model_manager import get_model_manager
model_manager = get_model_manager()
app.config['model_manager'] = model_manager

# Try to load latest model on startup
print("🔍 Looking for trained model...")
if model_manager.load_latest_model():
    print("✅ Model loaded successfully!")
else:
    print("ℹ️  No trained model found. Train a model to enable predictions.")


@app.route('/health')
def health():
    """Basic health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'session_id': current_session_id,
        'uptime': time.time() - session_start_time
    })


@app.route('/health/ready')
def health_ready():
    """Readiness probe - checks if service is ready to accept traffic."""
    try:
        # Check database connection
        db = app.config.get('db')
        if db:
            conn = db.connect()
            conn.execute("SELECT 1")
        
        # Check model manager
        model_manager = app.config.get('model_manager')
        model_loaded = model_manager.model_loaded if model_manager else False
        
        return jsonify({
            'status': 'ready',
            'database': 'connected',
            'model_loaded': model_loaded,
            'uptime': time.time() - session_start_time
        }), 200
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return jsonify({
            'status': 'not_ready',
            'error': str(e)
        }), 503


@app.route('/health/live')
def health_live():
    """Liveness probe - checks if service is alive."""
    return jsonify({
        'status': 'alive',
        'timestamp': time.time()
    }), 200


@app.route('/assets/<path:filename>')
def serve_spa_assets(filename):
    """Serve hashed Vite asset files."""
    asset_dir = spa_dist_dir / 'assets'
    return send_from_directory(asset_dir, filename)


@app.route('/vite.svg')
def serve_vite_icon():
    return send_from_directory(spa_dist_dir, 'vite.svg')


@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(spa_dist_dir, 'manifest.json')


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path: str):
    """Serve the React SPA for any non-API route."""
    if path.startswith('api'):
        return jsonify({'error': 'Not found'}), 404

    candidate = spa_dist_dir / path
    if path and candidate.exists():
        return send_from_directory(spa_dist_dir, path)

    return send_from_directory(spa_dist_dir, 'index.html')


if __name__ == '__main__':
    port = backend_config.get('port', 5000)
    debug = backend_config.get('debug', False)
    print(f"🚀 Starting KrypticTrack Backend Server...")
    print(f"📡 API running on http://localhost:{port}")
    print(f"🌐 SPA Dashboard: http://localhost:{port}/")
    print(f"   - All routes handled client-side (PWA-like)")
    app.run(host='0.0.0.0', port=port, debug=debug)


