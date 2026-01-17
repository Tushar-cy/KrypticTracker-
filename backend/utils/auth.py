"""Authentication utilities for API."""

from functools import wraps
from flask import request, jsonify
import os

# Simple API key authentication (local only)
API_KEY = os.getenv('KRYPTICTRACK_API_KEY', 'local-dev-key-change-in-production')


def require_api_key(f):
    """Decorator to require API key for endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function




