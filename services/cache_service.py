# services/cache_service.py
"""
High-performance Caching Service for Bale Downloader Bot.
Provides sub-millisecond caching using Redis with automatic JSON serialization
and a local in-memory fallback cache when Redis is unavailable.
"""

from collections import OrderedDict
import json
import logging
import os
import time
from typing import Any, Optional
from services.redis_client import get_async_redis, is_redis_available, mark_redis_failure

logger = logging.getLogger(__name__)

MAX_LOCAL_CACHE_SIZE = max(500, int(os.getenv("MAX_LOCAL_CACHE_SIZE", "5000")))

# Fallback in-memory O(1) LRU+TTL cache: OrderedDict[key, (value, expire_timestamp)]
_local_cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()


def _cleanup_local_cache():
    """Incrementally sample expired head entries and enforce MAX_LOCAL_CACHE_SIZE in O(1) LRU order."""
    now = time.monotonic()
    # Sample up to 64 oldest-used keys from the front instead of scanning all 5000 entries
    for _ in range(min(64, len(_local_cache))):
        k, (_, exp) = next(iter(_local_cache.items()))
        if exp < now:
            _local_cache.popitem(last=False)
        else:
            break
    if len(_local_cache) >= MAX_LOCAL_CACHE_SIZE:
        overflow = len(_local_cache) - MAX_LOCAL_CACHE_SIZE + max(1, MAX_LOCAL_CACHE_SIZE // 10)
        for _ in range(min(overflow, len(_local_cache))):
            _local_cache.popitem(last=False)


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
            mark_redis_failure(e)
            logger.debug("Redis cache_get error for %s: %s", key, e)

    # Local fallback
    if key in _local_cache:
        val, exp = _local_cache[key]
        if exp > time.monotonic():
            _local_cache.move_to_end(key)
            return val
        else:
            _local_cache.pop(key, None)

    return None


async def cache_set(key: str, value: Any, ttl_sec: int = 3600) -> bool:
    """Store an item in Redis cache or local fallback with a specified TTL."""
    redis = get_async_redis()
    if redis is not None:
        try:
            serialized = json.dumps(value, ensure_ascii=False)
            await redis.set(f"bale:cache:{key}", serialized, ex=max(1, ttl_sec))
            return True
        except Exception as e:
            mark_redis_failure(e)
            logger.debug("Redis cache_set error for %s: %s", key, e)

    # Local fallback
    if key not in _local_cache and len(_local_cache) >= MAX_LOCAL_CACHE_SIZE:
        _cleanup_local_cache()
    _local_cache[key] = (value, time.monotonic() + ttl_sec)
    _local_cache.move_to_end(key)
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
            mark_redis_failure(e)
            logger.debug("Redis cache_delete error for %s: %s", key, e)
    return True


async def cache_delete_many(keys: list[str]) -> bool:
    """Batch-delete multiple keys from Redis cache and local fallback."""
    if not keys:
        return True
    for k in keys:
        _local_cache.pop(k, None)
    redis = get_async_redis()
    if redis is not None:
        try:
            prefixed = [f"bale:cache:{k}" for k in keys]
            for i in range(0, len(prefixed), 500):
                await redis.delete(*prefixed[i : i + 500])
            return True
        except Exception as e:
            mark_redis_failure(e)
            logger.debug("Redis cache_delete_many error: %s", e)
    return True
