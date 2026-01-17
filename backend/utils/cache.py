"""Simple in-memory cache for query results."""

import time
from typing import Any, Optional, Dict
from functools import wraps
from threading import Lock

logger = None  # Will be initialized when needed


class SimpleCache:
    """Thread-safe in-memory cache with TTL."""
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default time-to-live in seconds
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            if time.time() > entry['expires_at']:
                del self._cache[key]
                return None
            
            return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        with self._lock:
            expires_at = time.time() + (ttl or self.default_ttl)
            self._cache[key] = {
                'value': value,
                'expires_at': expires_at
            }
    
    def delete(self, key: str) -> None:
        """Delete key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get number of cache entries."""
        with self._lock:
            return len(self._cache)


# Global cache instance
_cache = SimpleCache(default_ttl=300)


def cached(ttl: int = 300, key_func: Optional[callable] = None):
    """
    Decorator to cache function results.
    
    Args:
        ttl: Time-to-live in seconds
        key_func: Optional function to generate cache key from args/kwargs
        
    Usage:
        @cached(ttl=60)
        def expensive_function(arg1, arg2):
            # This result will be cached for 60 seconds
            return expensive_computation()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Try to get from cache
            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Compute value
            value = func(*args, **kwargs)
            
            # Store in cache
            _cache.set(cache_key, value, ttl)
            
            return value
        
        return wrapper
    return decorator


def get_cache() -> SimpleCache:
    """Get the global cache instance."""
    return _cache

