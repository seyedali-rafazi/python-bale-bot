# services/cache_service.py
"""
High-performance Caching Service for Bale Downloader Bot.
Provides sub-millisecond caching using Redis with automatic JSON serialization
and a local in-memory fallback cache when Redis is unavailable.
"""

import json
import logging
import time
from typing import Any, Optional
from services.redis_client import get_async_redis, is_redis_available

logger = logging.getLogger(__name__)

# Fallback in-memory cache: { key: (value, expire_timestamp) }
_local_cache: dict[str, tuple[Any, float]] = {}


def _cleanup_local_cache():
    """Remove expired keys from local cache to prevent memory leak."""
    now = time.time()
    expired = [k for k, (_, exp) in _local_cache.items() if exp < now]
    for k in expired:
        _local_cache.pop(k, None)


async def cache_get(key: str) -> Optional[Any]:
    """Retrieve an item from Redis cache or local in-memory fallback."""
    redis = get_async_redis()
    if redis is not None:
        try:
            val = await redis.get(f"bale:cache:{key}")
            if val is not None:
                try:
                    return json.loads(val)
                except Exception:
                    return val
        except Exception as e:
            logger.debug("Redis cache_get error for %s: %s", key, e)

    # Local fallback
    if key in _local_cache:
        val, exp = _local_cache[key]
        if exp > time.time():
            return val
        else:
            _local_cache.pop(key, None)

    return None


async def cache_set(key: str, value: Any, ttl_sec: int = 3600) -> bool:
    """Store an item in Redis cache or local fallback with a specified TTL."""
    redis = get_async_redis()
    if redis is not None:
        try:
            serialized = json.dumps(value, ensure_ascii=False) if not isinstance(value, (str, int, float, bool)) else str(value)
            await redis.set(f"bale:cache:{key}", serialized, ex=max(1, ttl_sec))
            return True
        except Exception as e:
            logger.debug("Redis cache_set error for %s: %s", key, e)

    # Local fallback
    if len(_local_cache) > 2000:
        _cleanup_local_cache()
    _local_cache[key] = (value, time.time() + ttl_sec)
    return True


async def cache_delete(key: str) -> bool:
    """Delete an item from Redis cache and local fallback."""
    _local_cache.pop(key, None)
    redis = get_async_redis()
    if redis is not None:
        try:
            await redis.delete(f"bale:cache:{key}")
            return True
        except Exception as e:
            logger.debug("Redis cache_delete error for %s: %s", key, e)
    return True
