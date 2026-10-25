# services/redis_client.py
"""
Redis Client Manager for Bale Downloader Bot.
Provides high-performance async and sync Redis connections with connection pooling,
automatic reconnection, health checks, and transparent fallback if Redis is unavailable.
"""

import os
import json
import logging
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").strip().lower() in ("true", "1", "yes")

_async_redis_client = None
_sync_redis_client = None
_redis_available = False
_warned_once = False


async def init_redis() -> bool:
    """Initialize the asynchronous Redis connection pool and verify connectivity."""
    global _async_redis_client, _redis_available, _warned_once

    if not REDIS_ENABLED:
        logger.info("ℹ️ Redis is disabled via REDIS_ENABLED=false")
        _redis_available = False
        return False

    try:
        import redis.asyncio as aioredis

        if _async_redis_client is None:
            _async_redis_client = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True,
                max_connections=50,
            )

        # Test connectivity
        await _async_redis_client.ping()
        _redis_available = True
        logger.info("⚡ Redis async client connected successfully: %s", REDIS_URL)
        return True

    except Exception as e:
        _redis_available = False
        if not _warned_once:
            logger.warning("⚠️ Redis connection failed (%s). Falling back gracefully to in-memory mode.", e)
            _warned_once = True
        return False


def get_sync_redis():
    """
    Get synchronous Redis client for backwards-compatible synchronous calls
    (such as state_manager). Falls back to None if unavailable.
    """
    global _sync_redis_client, _redis_available, _warned_once

    if not REDIS_ENABLED:
        return None

    if _sync_redis_client is not None:
        return _sync_redis_client

    try:
        import redis

        _sync_redis_client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            retry_on_timeout=True,
        )
        _sync_redis_client.ping()
        _redis_available = True
        return _sync_redis_client
    except Exception as e:
        if not _warned_once:
            logger.warning("⚠️ Sync Redis connection failed (%s). Falling back to in-memory.", e)
            _warned_once = True
        _sync_redis_client = None
        return None


def get_async_redis():
    """Get the async Redis client instance if available."""
    global _async_redis_client, _redis_available
    if _redis_available and _async_redis_client is not None:
        return _async_redis_client
    return None


def is_redis_available() -> bool:
    """Check if Redis is currently connected and operational."""
    return _redis_available


async def close_redis() -> None:
    """Close all Redis connections cleanly on application shutdown."""
    global _async_redis_client, _sync_redis_client, _redis_available

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
