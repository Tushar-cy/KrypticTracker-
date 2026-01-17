"""Decorators for API routes."""

from functools import wraps
from flask import request, jsonify
from backend.utils.validators import validate_request
from backend.utils.exceptions import ValidationError, DatabaseError, ModelError, LLMServiceError
from backend.utils.logger import get_logger
from typing import Type
from pydantic import BaseModel

logger = get_logger("api")


def validate_json(schema: Type[BaseModel]):
    """
    Decorator to validate JSON request body against a Pydantic schema.
    
    Usage:
        @api_bp.route('/endpoint', methods=['POST'])
        @validate_json(LogActionRequest)
        def endpoint():
            # request.validated_data contains validated data
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json() or {}
                validated_data = validate_request(data, schema)
                # Store validated data in request object
                request.validated_data = validated_data
                return f(*args, **kwargs)
            except ValidationError as e:
                logger.warning("Validation error", errors=e.details.get('errors', []))
                return jsonify({
                    'error': e.message,
                    'error_code': e.error_code,
                    'details': e.details
                }), 400
        return decorated_function
    return decorator


def handle_errors(f):
    """
    Decorator to handle common exceptions and return appropriate HTTP responses.
    
    Usage:
        @api_bp.route('/endpoint')
        @handle_errors
        def endpoint():
            # Your code here
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            logger.warning("Validation error", error=e.message, details=e.details)
            return jsonify({
                'error': e.message,
                'error_code': e.error_code,
                'details': e.details
            }), 400
        except DatabaseError as e:
            logger.error("Database error", error=e.message, details=e.details)
            return jsonify({
                'error': 'Database operation failed',
                'error_code': 'DATABASE_ERROR'
            }), 500
        except ModelError as e:
            logger.error("Model error", error=e.message, details=e.details)
            return jsonify({
                'error': 'Model operation failed',
                'error_code': 'MODEL_ERROR',
                'details': e.details
            }), 500
        except LLMServiceError as e:
            logger.error("LLM service error", error=e.message, details=e.details)
            return jsonify({
                'error': 'LLM service unavailable',
                'error_code': 'LLM_ERROR',
                'details': e.details
            }), 503
        except Exception as e:
            logger.error("Unexpected error", error=str(e), exc_info=True)
            return jsonify({
                'error': 'Internal server error',
                'error_code': 'INTERNAL_ERROR'
            }), 500
    return decorated_function

