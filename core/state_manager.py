# core/state_manager.py
"""
Persistent State Manager for Bale Downloader Bot.
Provides dual-layer caching (L1 Memory with TTL & LRU eviction + L2 Redis).
Maintains 100% backward compatibility with existing synchronous calls,
while never blocking the asyncio event loop on synchronous Redis I/O.
"""

import asyncio
from collections import OrderedDict
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

_state_versions: OrderedDict[str, int] = OrderedDict()
_version_seq: int = 0
_version_lock = threading.Lock()
_pending_redis_tasks: set[asyncio.Task] = set()


class StateCache(MutableMapping):
    """
    In-memory thread-safe state cache with TTL expiration and LRU capacity eviction.
    Implements MutableMapping to maintain 100% backward compatibility with dict operations.
    """

    def __init__(self, max_capacity: int = 10000, default_ttl: float = 7200.0, on_evict=None):
        self._data: OrderedDict = OrderedDict()
        self._expires: dict = {}
        self._max_capacity = max_capacity
        self._default_ttl = default_ttl
        self._on_evict = on_evict
        self._lock = threading.RLock()

    def _notify_evicted(self, items: list) -> None:
        if not items or not self._on_evict:
            return
        for key, value in items:
            try:
                self._on_evict(key, value)
            except Exception as e:
                logger.debug("StateCache on_evict callback error for %s: %s", key, e)

    def __getitem__(self, key):
        evicted_val = None
        expired = False
        with self._lock:
            now = time.time()
            if key not in self._data:
                raise KeyError(key)
            if now > self._expires.get(key, 0):
                evicted_val = self._remove_key(key)
                expired = True
            else:
                self._data.move_to_end(key)
                return self._data[key]
        if expired:
            self._notify_evicted([(key, evicted_val)])
        raise KeyError(key)

    def __setitem__(self, key, value):
        evicted: list = []
        with self._lock:
            now = time.time()
            if key not in self._data and len(self._data) >= self._max_capacity:
                evicted = self._evict_over_capacity(now)
            self._data[key] = value
            self._data.move_to_end(key)
            self._expires[key] = now + self._default_ttl
        self._notify_evicted(evicted)

    def __delitem__(self, key):
        with self._lock:
            if key in self._data:
                self._remove_key(key)
            else:
                raise KeyError(key)

    def __iter__(self):
        evicted: list = []
        with self._lock:
            evicted = self._purge_expired()
            keys = list(self._data.keys())
        self._notify_evicted(evicted)
        return iter(keys)

    def __len__(self):
        evicted: list = []
        with self._lock:
            evicted = self._purge_expired()
            length = len(self._data)
        self._notify_evicted(evicted)
        return length

    def __contains__(self, key):
        evicted_val = None
        expired = False
        with self._lock:
            now = time.time()
            if key not in self._data:
                return False
            if now > self._expires.get(key, 0):
                evicted_val = self._remove_key(key)
                expired = True
            else:
                return True
        if expired:
            self._notify_evicted([(key, evicted_val)])
        return False

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
        val = self._data.pop(key, None)
        self._expires.pop(key, None)
        return val

    def _purge_expired(self) -> list:
        now = time.time()
        expired = [k for k, exp in self._expires.items() if now > exp]
        evicted = []
        for k in expired:
            evicted.append((k, self._remove_key(k)))
        return evicted

    def _evict_over_capacity(self, now: float) -> list:
        evicted = self._purge_expired()
        if len(self._data) >= self._max_capacity:
            to_evict_count = max(1, int(self._max_capacity * 0.1))
            for _ in range(min(to_evict_count, len(self._data))):
                oldest_key, oldest_val = self._data.popitem(last=False)
                self._expires.pop(oldest_key, None)
                evicted.append((oldest_key, oldest_val))
        return evicted


# L1 In-Memory Cache with TTL & LRU bounds
user_states: StateCache = StateCache(
    max_capacity=MAX_MEMORY_STATES,
    default_ttl=float(STATE_TTL_SECONDS),
)


def _make_key(chat_id) -> str:
    return f"bale:state:{chat_id}"


def _next_version(chat_id) -> int:
    global _version_seq
    key = str(chat_id)
    with _version_lock:
        _version_seq += 1
        ver = _version_seq
        _state_versions[key] = ver
        _state_versions.move_to_end(key)
        max_ver_entries = MAX_MEMORY_STATES * 2
        while len(_state_versions) > max_ver_entries:
            _state_versions.popitem(last=False)
        return ver


def _is_latest_version(chat_id, version: int) -> bool:
    key = str(chat_id)
    with _version_lock:
        latest = _state_versions.get(key)
        return latest is None or latest == version


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
    key = str(chat_id)
    state_data = {"step": step}
    state_data.update(kwargs)
    user_states[key] = state_data
    version = _next_version(key)
    serialized = json.dumps(state_data, ensure_ascii=False, default=str)

    loop = _get_running_loop_or_none()
    if loop is not None:
        _schedule_async_task(loop, _persist_state_async(key, serialized, version))
        return

    # Sync fallback only outside an active event loop (e.g., sync CLI/tests)
    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            sync_redis.set(_make_key(key), serialized, ex=STATE_TTL_SECONDS)
        except Exception as e:
            logger.debug("Failed to persist state to Redis for %s: %s", key, e)


def get_state(chat_id) -> dict:
    """
    Get user state synchronously. Prefer async_get_state() in async handlers.
    Checks L1 memory first; falls back to sync Redis only outside a running event loop.
    """
    key = str(chat_id)
    cached = user_states.get(key)
    if cached is not None:
        return cached

    try:
        asyncio.get_running_loop()
        # Never block a live event loop with sync Redis I/O
        return {}
    except RuntimeError:
        pass

    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            val = sync_redis.get(_make_key(key))
            if val:
                data = json.loads(val)
                user_states[key] = data
                return data
        except Exception as e:
            logger.debug("Failed to retrieve state from Redis for %s: %s", key, e)

    return {}


def clear_state(chat_id):
    """
    Clear user state from both local memory and Redis without blocking the event loop.
    """
    key = str(chat_id)
    user_states.pop(key, None)
    version = _next_version(key)

    loop = _get_running_loop_or_none()
    if loop is not None:
        _schedule_async_task(loop, _delete_state_async(key, version))
        return

    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            sync_redis.delete(_make_key(key))
        except Exception as e:
            logger.debug("Failed to clear state in Redis for %s: %s", key, e)


# =========================================================
# ASYNC API
# =========================================================

async def async_set_state(chat_id, step, **kwargs):
    key = str(chat_id)
    state_data = {"step": step}
    state_data.update(kwargs)
    user_states[key] = state_data
    version = _next_version(key)

    redis = get_async_redis()
    if redis is not None:
        try:
            serialized = json.dumps(state_data, ensure_ascii=False, default=str)
            if _is_latest_version(key, version):
                await redis.set(_make_key(key), serialized, ex=STATE_TTL_SECONDS)
        except Exception as e:
            logger.debug("Async Redis set_state failed for %s: %s", key, e)


async def async_get_state(chat_id) -> dict:
    key = str(chat_id)
    cached = user_states.get(key)
    if cached is not None:
        return cached

    redis = get_async_redis()
    if redis is not None:
        try:
            val = await redis.get(_make_key(key))
            if val:
                data = json.loads(val)
                user_states[key] = data
                return data
        except Exception as e:
            logger.debug("Async Redis get_state failed for %s: %s", key, e)

    return {}


async def async_clear_state(chat_id):
    key = str(chat_id)
    user_states.pop(key, None)
    version = _next_version(key)

    redis = get_async_redis()
    if redis is not None:
        try:
            if _is_latest_version(key, version):
                await redis.delete(_make_key(key))
        except Exception as e:
            logger.debug("Async Redis clear_state failed for %s: %s", key, e)
