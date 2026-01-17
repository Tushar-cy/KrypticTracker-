"""Custom exceptions for KrypticTrack."""

from typing import Optional, Dict, Any


class KrypticTrackError(Exception):
    """Base exception for all KrypticTrack errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseError(KrypticTrackError):
    """Database operation failed."""
    pass


class ValidationError(KrypticTrackError):
    """Input validation failed."""
    pass


class ModelError(KrypticTrackError):
    """Model operation failed (loading, training, prediction)."""
    pass


class LLMServiceError(KrypticTrackError):
    """LLM service operation failed."""
    pass


class ConfigurationError(KrypticTrackError):
    """Configuration error."""
    pass


class RateLimitError(KrypticTrackError):
    """Rate limit exceeded."""
    pass

