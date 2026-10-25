# services/rate_limiter.py
"""
Redis-based Rate Limiter & Concurrency Lock Manager.
Provides atomic rate limiting, user action locking (preventing double-click/spam),
anti-flood checks, and daily usage caching.
"""

import time
import logging
from contextlib import asynccontextmanager
from typing import Optional
from services.redis_client import get_async_redis

logger = logging.getLogger(__name__)

# Fallback locks in memory if Redis is absent
_local_locks: set[str] = set()
_local_flood_tracker: dict[str, list[float]] = {}


@asynccontextmanager
async def user_action_lock(user_id: str | int, action: str, timeout_sec: int = 30):
    """
    Distributed async lock to prevent race conditions and duplicate operations
    (e.g., user rapidly pressing download buttons).
    
    Usage:
        async with user_action_lock(user_id, "yt_download", timeout_sec=60) as acquired:
            if not acquired:
                await send_message("عملیات قبلی هنوز در حال اجرا است...")
                return
            ...
    """
    lock_key = f"bale:lock:{action}:{user_id}"
    redis = get_async_redis()
    acquired = False

    try:
        if redis is not None:
            # Atomic SET NX EX in Redis
            res = await redis.set(lock_key, "locked", nx=True, ex=timeout_sec)
            acquired = bool(res)
        else:
            # In-memory lock fallback
            if lock_key not in _local_locks:
                _local_locks.add(lock_key)
                acquired = True
            else:
                acquired = False

        yield acquired

    finally:
        if acquired:
            try:
                if redis is not None:
                    await redis.delete(lock_key)
                else:
                    _local_locks.discard(lock_key)
            except Exception as e:
                logger.debug("Error releasing lock for %s: %s", lock_key, e)


async def check_anti_flood(user_id: str | int, max_messages: int = 5, window_sec: int = 3) -> bool:
    """
    Anti-flood check: Returns True if user is within allowed limits,
    or False if user is flooding/spamming the bot.
    """
    uid_str = str(user_id)
    now = time.time()
    redis = get_async_redis()

    if redis is not None:
        try:
            flood_key = f"bale:flood:{uid_str}"
            pipe = redis.pipeline()
            pipe.incr(flood_key)
            pipe.expire(flood_key, window_sec)
            results = await pipe.execute()
            count = results[0]
            return count <= max_messages
        except Exception as e:
            logger.debug("Redis anti-flood check error: %s", e)

    # Local fallback
    timestamps = _local_flood_tracker.get(uid_str, [])
    cutoff = now - window_sec
    valid_timestamps = [t for t in timestamps if t > cutoff]
    valid_timestamps.append(now)
    _local_flood_tracker[uid_str] = valid_timestamps

    # Clean old keys occasionally
    if len(_local_flood_tracker) > 5000:
        for k in list(_local_flood_tracker.keys()):
            if not _local_flood_tracker[k] or _local_flood_tracker[k][-1] < cutoff:
                _local_flood_tracker.pop(k, None)

    return len(valid_timestamps) <= max_messages


async def get_cached_daily_usage(service: str, user_id: str | int, today_str: str) -> Optional[int]:
    """Retrieve daily usage count from Redis cache."""
    redis = get_async_redis()
    if redis is not None:
        try:
            key = f"bale:usage:{service}:{user_id}:{today_str}"
            val = await redis.get(key)
            if val is not None:
                return int(val)
        except Exception as e:
            logger.debug("Redis get_cached_daily_usage error: %s", e)
    return None


async def set_cached_daily_usage(service: str, user_id: str | int, today_str: str, count: int, ttl_sec: int = 86400) -> None:
    """Cache daily usage count in Redis with 24-hour expiration."""
    redis = get_async_redis()
    if redis is not None:
        try:
            key = f"bale:usage:{service}:{user_id}:{today_str}"
            await redis.set(key, count, ex=ttl_sec)
        except Exception as e:
            logger.debug("Redis set_cached_daily_usage error: %s", e)


async def incr_cached_daily_usage(service: str, user_id: str | int, today_str: str, ttl_sec: int = 86400) -> int:
    """Atomically increment daily usage count in Redis and set TTL."""
    redis = get_async_redis()
    if redis is not None:
        try:
            key = f"bale:usage:{service}:{user_id}:{today_str}"
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_sec)
            results = await pipe.execute()
            return int(results[0])
        except Exception as e:
            logger.debug("Redis incr_cached_daily_usage error: %s", e)
    return -1


async def invalidate_cached_usage(user_id: str | int, service: Optional[str] = None) -> None:
    """Clear cached usage for a user (e.g. upon admin reset)."""
    redis = get_async_redis()
    if redis is not None:
        try:
            pattern = f"bale:usage:{service or '*'}:{user_id}:*"
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
        except Exception as e:
            logger.debug("Redis invalidate_cached_usage error: %s", e)
