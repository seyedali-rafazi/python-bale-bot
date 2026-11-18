# services/redis_client.py
"""
Redis Client Manager for Bale Downloader Bot.
Provides high-performance async and sync Redis connections with connection pooling,
automatic reconnection, health checks, and transparent fallback if Redis is unavailable.
"""

import asyncio
import os
import json
import logging
import threading
import time
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").strip().lower() in ("true", "1", "yes")
REDIS_RETRY_COOLDOWN_SEC = max(5.0, float(os.getenv("REDIS_RETRY_COOLDOWN_SEC", "20")))

_async_redis_client = None
_async_redis_lock = asyncio.Lock()
_sync_redis_client = None
_sync_redis_lock = threading.Lock()
_redis_available = False
_warned_once = False
_async_retry_after = 0.0
_sync_retry_after = 0.0
_async_reconnect_task: Optional[asyncio.Task] = None


def _is_connection_error(exc: Exception | None) -> bool:
    if exc is None:
        return True
    if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
        return True
    mod = type(exc).__module__ or ""
    if mod.startswith("redis."):
        name = type(exc).__name__
        if name in (
            "ConnectionError",
            "TimeoutError",
            "BusyLoadingError",
            "ClusterDownError",
            "ReadOnlyError",
        ):
            return True
    return False


def mark_redis_failure(exc: Exception | None = None, *, is_sync: bool = False) -> None:
    """Temporarily trip circuit breaker on Redis connection/timeout failures."""
    global _async_retry_after, _sync_retry_after
    if not _is_connection_error(exc):
        return
    until = time.monotonic() + REDIS_RETRY_COOLDOWN_SEC
    if is_sync:
        _sync_retry_after = until
    else:
        _async_retry_after = until


async def init_redis() -> bool:
    """Initialize the asynchronous Redis connection pool and verify connectivity."""
    global _async_redis_client, _redis_available, _warned_once, _async_retry_after

    if not REDIS_ENABLED:
        logger.info("ℹ️ Redis is disabled via REDIS_ENABLED=false")
        _redis_available = False
        return False

    async with _async_redis_lock:
        try:
            import redis.asyncio as aioredis

            if _async_redis_client is None:
                _async_redis_client = aioredis.from_url(
                    REDIS_URL,
                    decode_responses=True,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    max_connections=50,
                )

            # Test connectivity
            await _async_redis_client.ping()
            _redis_available = True
            _async_retry_after = 0.0
            logger.info("⚡ Redis async client connected successfully: %s", REDIS_URL)
            return True

        except Exception as e:
            _redis_available = False
            _async_retry_after = time.monotonic() + REDIS_RETRY_COOLDOWN_SEC
            if _async_redis_client is not None:
                try:
                    await _async_redis_client.aclose()
                except Exception:
                    pass
                _async_redis_client = None
            if not _warned_once:
                logger.warning("⚠️ Redis connection failed (%s). Falling back gracefully to in-memory mode.", e)
                _warned_once = True
            return False


def get_sync_redis():
    """
    Get synchronous Redis client for backwards-compatible synchronous calls
    (such as state_manager). Falls back to None if unavailable.
    """
    global _sync_redis_client, _redis_available, _warned_once, _sync_retry_after

    if not REDIS_ENABLED:
        return None

    if _sync_redis_client is not None:
        if time.monotonic() < _sync_retry_after:
            return None
        return _sync_redis_client

    if time.monotonic() < _sync_retry_after:
        return None

    with _sync_redis_lock:
        if _sync_redis_client is not None:
            return None if time.monotonic() < _sync_retry_after else _sync_redis_client
        if time.monotonic() < _sync_retry_after:
            return None
        try:
            import redis

            _sync_redis_client = redis.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                retry_on_timeout=True,
                health_check_interval=30,
                max_connections=25,
            )
            _sync_redis_client.ping()
            _redis_available = True
            _sync_retry_after = 0.0
            return _sync_redis_client
        except Exception as e:
            _sync_retry_after = time.monotonic() + REDIS_RETRY_COOLDOWN_SEC
            if _sync_redis_client is not None:
                try:
                    _sync_redis_client.close()
                except Exception:
                    pass
            _sync_redis_client = None
            if not _warned_once:
                logger.warning("⚠️ Sync Redis connection failed (%s). Falling back to in-memory.", e)
                _warned_once = True
            return None


def _schedule_async_reconnect() -> None:
    global _async_reconnect_task
    if _async_reconnect_task is not None and not _async_reconnect_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _reconnect() -> None:
        try:
            await init_redis()
        except Exception:
            pass

    _async_reconnect_task = loop.create_task(_reconnect())


def get_async_redis():
    """Get the async Redis client instance if available and circuit breaker is closed."""
    global _async_redis_client, _redis_available
    if _redis_available and _async_redis_client is not None:
        if time.monotonic() < _async_retry_after:
            return None
        return _async_redis_client
    if REDIS_ENABLED and _async_retry_after > 0 and time.monotonic() >= _async_retry_after:
        _schedule_async_reconnect()
    return None


def is_redis_available() -> bool:
    """Check if Redis is currently connected and operational."""
    return _redis_available


async def close_redis() -> None:
    """Close all Redis connections cleanly on application shutdown."""
    global _async_redis_client, _sync_redis_client, _redis_available, _async_reconnect_task

    if _async_reconnect_task is not None and not _async_reconnect_task.done():
        _async_reconnect_task.cancel()
        try:
            await _async_reconnect_task
        except (asyncio.CancelledError, Exception):
            pass
    _async_reconnect_task = None

    if _async_redis_client is not None:
        try:
            await _async_redis_client.aclose()
            logger.info("✅ Redis async connection closed.")
        except Exception:
            logger.exception("Error closing async Redis connection")
        _async_redis_client = None

    if _sync_redis_client is not None:
        try:
            _sync_redis_client.close()
            logger.info("✅ Redis sync connection closed.")
        except Exception:
            logger.exception("Error closing sync Redis connection")
        _sync_redis_client = None

    _redis_available = False
