# services/rate_limiter.py
"""
Redis-based Rate Limiter & Concurrency Lock Manager.
Provides atomic rate limiting, user action locking (preventing double-click/spam),
anti-flood checks, and daily usage caching.
"""

from collections import OrderedDict
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional
from services.redis_client import get_async_redis, mark_redis_failure

logger = logging.getLogger(__name__)

# Fallback locks in memory if Redis is absent: OrderedDict[lock_key, (token, expire_ts)]
_local_locks: OrderedDict[str, tuple[str, float]] = OrderedDict()
_local_flood_tracker: OrderedDict[str, list[float]] = OrderedDict()

_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_ANTI_FLOOD_LUA = """
local count = redis.call("incr", KEYS[1])
if count == 1 then
    redis.call("expire", KEYS[1], ARGV[1])
end
return count
"""


@asynccontextmanager
async def user_action_lock(user_id: str | int, action: str, timeout_sec: int = 30):
    """
    Distributed async lock to prevent race conditions and duplicate operations
    (e.g., user rapidly pressing download buttons).
    Uses a unique owner token so expired locks never release another holder's lock.
    """
    lock_key = f"bale:lock:{action}:{user_id}"
    lock_token = uuid.uuid4().hex
    redis = get_async_redis()
    acquired = False

    try:
        if redis is not None:
            try:
                # Atomic SET NX EX in Redis with unique owner token
                res = await redis.set(lock_key, lock_token, nx=True, ex=timeout_sec)
                acquired = bool(res)
            except Exception as e:
                mark_redis_failure(e)
                logger.debug("Redis user_action_lock error for %s, falling back to local: %s", lock_key, e)
                redis = None

        if redis is None:
            # In-memory lock fallback with O(1) incremental TTL/LRU eviction
            now = time.monotonic()
            if len(_local_locks) > 5000:
                for _ in range(min(128, len(_local_locks))):
                    _, (_, exp) = next(iter(_local_locks.items()))
                    if now >= exp:
                        _local_locks.popitem(last=False)
                    else:
                        break
                while len(_local_locks) > 4500:
                    _local_locks.popitem(last=False)
            existing = _local_locks.get(lock_key)
            if existing is None or now >= existing[1]:
                _local_locks[lock_key] = (lock_token, now + timeout_sec)
                _local_locks.move_to_end(lock_key)
                acquired = True
            else:
                acquired = False

        yield acquired

    finally:
        if acquired:
            try:
                if redis is not None:
                    await redis.eval(_RELEASE_LOCK_LUA, 1, lock_key, lock_token)
                else:
                    existing = _local_locks.get(lock_key)
                    if existing and existing[0] == lock_token:
                        _local_locks.pop(lock_key, None)
            except Exception as e:
                logger.debug("Error releasing lock for %s: %s", lock_key, e)


async def check_anti_flood(user_id: str | int, max_messages: int = 5, window_sec: int = 3) -> bool:
    """
    Anti-flood check: Returns True if user is within allowed limits,
    or False if user is flooding/spamming the bot.
    """
    uid_str = str(user_id)
    now = time.monotonic()
    redis = get_async_redis()

    if redis is not None:
        try:
            flood_key = f"bale:flood:{uid_str}"
            count = int(await redis.eval(_ANTI_FLOOD_LUA, 1, flood_key, window_sec))
            return count <= max_messages
        except Exception as e:
            mark_redis_failure(e)
            logger.debug("Redis anti-flood check error: %s", e)

    # Local fallback
    timestamps = _local_flood_tracker.get(uid_str, [])
    cutoff = now - window_sec
    valid_timestamps = [t for t in timestamps if t > cutoff]
    valid_timestamps.append(now)
    _local_flood_tracker[uid_str] = valid_timestamps
    _local_flood_tracker.move_to_end(uid_str)

    # Incremental head purge + LRU bound in O(1)
    if len(_local_flood_tracker) > 5000:
        for _ in range(min(128, len(_local_flood_tracker))):
            _, ts_list = next(iter(_local_flood_tracker.items()))
            if not ts_list or ts_list[-1] < cutoff:
                _local_flood_tracker.popitem(last=False)
            else:
                break
        while len(_local_flood_tracker) > 4500:
            _local_flood_tracker.popitem(last=False)

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


async def _delete_by_scan(redis, pattern: str) -> None:
    """Non-blocking key deletion using SCAN instead of O(N) KEYS."""
    batch: list[str] = []
    async for key in redis.scan_iter(match=pattern, count=500):
        batch.append(key)
        if len(batch) >= 500:
            await redis.delete(*batch)
            batch.clear()
    if batch:
        await redis.delete(*batch)


async def delete_cached_daily_usage(service: str, user_id: str | int, period_key: str) -> None:
    """O(1) deletion of a single cached period-usage key."""
    redis = get_async_redis()
    if redis is not None:
        try:
            await redis.delete(f"bale:usage:{service}:{user_id}:{period_key}")
        except Exception as e:
            logger.debug("Redis delete_cached_daily_usage error: %s", e)


async def invalidate_cached_usage(user_id: str | int, service: Optional[str] = None) -> None:
    """Clear cached usage for a user (e.g. upon admin reset)."""
    redis = get_async_redis()
    if redis is not None:
        try:
            pattern = f"bale:usage:{service or '*'}:{user_id}:*"
            await _delete_by_scan(redis, pattern)
        except Exception as e:
            logger.debug("Redis invalidate_cached_usage error: %s", e)


async def invalidate_all_cached_usage() -> None:
    """Clear all cached daily usage keys (e.g. upon global admin reset)."""
    redis = get_async_redis()
    if redis is not None:
        try:
            await _delete_by_scan(redis, "bale:usage:*")
        except Exception as e:
            logger.debug("Redis invalidate_all_cached_usage error: %s", e)
