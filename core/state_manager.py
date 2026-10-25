# core/state_manager.py
"""
Persistent State Manager for Bale Downloader Bot.
Provides dual-layer caching (L1 Memory + L2 Redis).
Maintains 100% backward compatibility with existing synchronous calls,
while persisting states across bot restarts and automatic TTL cleanup via Redis.
"""

import json
import logging
from services.redis_client import get_sync_redis, get_async_redis

logger = logging.getLogger(__name__)

# L1 In-Memory Cache for 0ms lookup
user_states: dict = {}

STATE_TTL_SECONDS = 7200  # 2 hours


def _make_key(chat_id) -> str:
    return f"bale:state:{chat_id}"


def set_state(chat_id, step, **kwargs):
    """
    Set user state in local memory and sync to Redis with TTL.
    """
    state_data = {"step": step}
    state_data.update(kwargs)
    user_states[chat_id] = state_data

    # Persist to Redis (L2)
    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            serialized = json.dumps(state_data, ensure_ascii=False, default=str)
            sync_redis.set(_make_key(chat_id), serialized, ex=STATE_TTL_SECONDS)
        except Exception as e:
            logger.debug("Failed to persist state to Redis for %s: %s", chat_id, e)


def get_state(chat_id) -> dict:
    """
    Get user state. Checks L1 memory first; if not found (e.g. after bot restart),
    fetches from Redis, repopulates L1 memory, and returns state.
    """
    if chat_id in user_states:
        return user_states[chat_id]

    # Check Redis (L2)
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
    Clear user state from both local memory and Redis.
    """
    if chat_id in user_states:
        del user_states[chat_id]

    sync_redis = get_sync_redis()
    if sync_redis is not None:
        try:
            sync_redis.delete(_make_key(chat_id))
        except Exception as e:
            logger.debug("Failed to clear state in Redis for %s: %s", chat_id, e)


# =========================================================
# ASYNC API (For modern async handlers if needed)
# =========================================================

async def async_set_state(chat_id, step, **kwargs):
    state_data = {"step": step}
    state_data.update(kwargs)
    user_states[chat_id] = state_data

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
    if chat_id in user_states:
        del user_states[chat_id]

    redis = get_async_redis()
    if redis is not None:
        try:
            await redis.delete(_make_key(chat_id))
        except Exception as e:
            logger.debug("Async Redis clear_state failed for %s: %s", chat_id, e)
