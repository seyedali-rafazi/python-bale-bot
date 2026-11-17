# core/state_manager.py
"""
Persistent State Manager for Bale Downloader Bot.
Provides dual-layer caching (L1 Memory with TTL & LRU eviction + L2 Redis).
Maintains 100% backward compatibility with existing synchronous calls,
while never blocking the asyncio event loop on synchronous Redis I/O.
"""

import asyncio
from collections.abc import MutableMapping
import json
import logging
import os
import threading
import time
from services.redis_client import get_sync_redis, get_async_redis

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = int(os.getenv("STATE_TTL_SECONDS", "7200"))  # 2 hours
MAX_MEMORY_STATES = int(os.getenv("MAX_MEMORY_STATES", "10000"))

_state_versions: dict[str, int] = {}
_version_lock = threading.Lock()
_pending_redis_tasks: set[asyncio.Task] = set()


class StateCache(MutableMapping):
    """
    In-memory thread-safe state cache with TTL expiration and LRU capacity eviction.
    Implements MutableMapping to maintain 100% backward compatibility with dict operations.
    """

    def __init__(self, max_capacity: int = 10000, default_ttl: float = 7200.0):
        self._data: dict = {}
        self._expires: dict = {}
        self._last_access: dict = {}
        self._max_capacity = max_capacity
        self._default_ttl = default_ttl
        self._lock = threading.RLock()

    def __getitem__(self, key):
        with self._lock:
            now = time.time()
            if key not in self._data:
                raise KeyError(key)
            if now > self._expires.get(key, 0):
                self._remove_key(key)
                raise KeyError(key)
            self._last_access[key] = now
            return self._data[key]

    def __setitem__(self, key, value):
        with self._lock:
            now = time.time()
            if key not in self._data and len(self._data) >= self._max_capacity:
                self._evict_over_capacity(now)
            self._data[key] = value
            self._expires[key] = now + self._default_ttl
            self._last_access[key] = now

    def __delitem__(self, key):
        with self._lock:
            if key in self._data:
                self._remove_key(key)
            else:
                raise KeyError(key)

    def __iter__(self):
        with self._lock:
            self._purge_expired()
            return iter(list(self._data.keys()))

    def __len__(self):
        with self._lock:
            self._purge_expired()
            return len(self._data)

    def __contains__(self, key):
        with self._lock:
            now = time.time()
            if key not in self._data:
                return False
            if now > self._expires.get(key, 0):
                self._remove_key(key)
                return False
            return True

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, default=None):
        with self._lock:
            try:
                val = self[key]
                self._remove_key(key)
                return val
            except KeyError:
                return default

    def _remove_key(self, key):
        self._data.pop(key, None)
        self._expires.pop(key, None)
        self._last_access.pop(key, None)

    def _purge_expired(self):
        now = time.time()
        expired = [k for k, exp in self._expires.items() if now > exp]
        for k in expired:
            self._remove_key(k)

    def _evict_over_capacity(self, now: float):
        self._purge_expired()
        if len(self._data) >= self._max_capacity:
            to_evict_count = max(1, int(self._max_capacity * 0.1))
            sorted_keys = sorted(self._last_access.keys(), key=lambda k: self._last_access[k])
            for k in sorted_keys[:to_evict_count]:
                self._remove_key(k)


# L1 In-Memory Cache with TTL & LRU bounds
user_states: StateCache = StateCache(
    max_capacity=MAX_MEMORY_STATES,
    default_ttl=float(STATE_TTL_SECONDS),
)


def _make_key(chat_id) -> str:
    return f"bale:state:{chat_id}"


def _next_version(chat_id) -> int:
    key = str(chat_id)
    with _version_lock:
        if len(_state_versions) > MAX_MEMORY_STATES * 2:
            # Keep memory bounded; active keys will get new versions cleanly
            _state_versions.clear()
        ver = _state_versions.get(key, 0) + 1
        _state_versions[key] = ver
        return ver


def _is_latest_version(chat_id, version: int) -> bool:
    key = str(chat_id)
    with _version_lock:
        return _state_versions.get(key, version) == version


def _get_running_loop_or_none():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _schedule_async_task(loop, coro) -> None:
    task = loop.create_task(coro)
    _pending_redis_tasks.add(task)
    task.add_done_callback(_pending_redis_tasks.discard)


async def _persist_state_async(chat_id, serialized: str, version: int) -> None:
    redis = get_async_redis()
    if redis is None or not _is_latest_version(chat_id, version):
        return
    try:
        await redis.set(_make_key(chat_id), serialized, ex=STATE_TTL_SECONDS)
    except Exception as e:
        logger.debug("Async Redis background set_state failed for %s: %s", chat_id, e)


async def _delete_state_async(chat_id, version: int) -> None:
    redis = get_async_redis()
    if redis is None or not _is_latest_version(chat_id, version):
        return
    try:
        await redis.delete(_make_key(chat_id))
    except Exception as e:
        logger.debug("Async Redis background clear_state failed for %s: %s", chat_id, e)


def set_state(chat_id, step, **kwargs):
    """
    Set user state in local memory (L1) and persist to Redis (L2) with TTL.
    Uses non-blocking async Redis when called inside a running asyncio event loop.
    """
    state_data = {"step": step}
    state_data.update(kwargs)
    user_states[chat_id] = state_data
    version = _next_version(chat_id)
    serialized = json.dumps(state_data, ensure_ascii=False, default=str)

    loop = _get_running_loop_or_none()
    if loop is not None:
        _schedule_async_task(loop, _persist_state_async(chat_id, serialized, version))
        return

    # Sync fallback only outside an active event loop (e.g., sync CLI/tests)
    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            sync_redis.set(_make_key(chat_id), serialized, ex=STATE_TTL_SECONDS)
        except Exception as e:
            logger.debug("Failed to persist state to Redis for %s: %s", chat_id, e)


def get_state(chat_id) -> dict:
    """
    Get user state synchronously. Prefer async_get_state() in async handlers.
    Checks L1 memory first; falls back to sync Redis only outside a running event loop.
    """
    if chat_id in user_states:
        return user_states[chat_id]

    try:
        asyncio.get_running_loop()
        # Never block a live event loop with sync Redis I/O
        return {}
    except RuntimeError:
        pass

    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            val = sync_redis.get(_make_key(chat_id))
            if val:
                data = json.loads(val)
                user_states[chat_id] = data
                return data
        except Exception as e:
            logger.debug("Failed to retrieve state from Redis for %s: %s", chat_id, e)

    return {}


def clear_state(chat_id):
    """
    Clear user state from both local memory and Redis without blocking the event loop.
    """
    user_states.pop(chat_id, None)
    version = _next_version(chat_id)

    loop = _get_running_loop_or_none()
    if loop is not None:
        _schedule_async_task(loop, _delete_state_async(chat_id, version))
        return

    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            sync_redis.delete(_make_key(chat_id))
        except Exception as e:
            logger.debug("Failed to clear state in Redis for %s: %s", chat_id, e)


# =========================================================
# ASYNC API
# =========================================================

async def async_set_state(chat_id, step, **kwargs):
    state_data = {"step": step}
    state_data.update(kwargs)
    user_states[chat_id] = state_data
    _next_version(chat_id)

    redis = get_async_redis()
    if redis is not None:
        try:
            serialized = json.dumps(state_data, ensure_ascii=False, default=str)
            await redis.set(_make_key(chat_id), serialized, ex=STATE_TTL_SECONDS)
        except Exception as e:
            logger.debug("Async Redis set_state failed for %s: %s", chat_id, e)


async def async_get_state(chat_id) -> dict:
    if chat_id in user_states:
        return user_states[chat_id]

    redis = get_async_redis()
    if redis is not None:
        try:
            val = await redis.get(_make_key(chat_id))
            if val:
                data = json.loads(val)
                user_states[chat_id] = data
                return data
        except Exception as e:
            logger.debug("Async Redis get_state failed for %s: %s", chat_id, e)

    return {}


async def async_clear_state(chat_id):
    user_states.pop(chat_id, None)
    _next_version(chat_id)

    redis = get_async_redis()
    if redis is not None:
        try:
            await redis.delete(_make_key(chat_id))
        except Exception as e:
            logger.debug("Async Redis clear_state failed for %s: %s", chat_id, e)
