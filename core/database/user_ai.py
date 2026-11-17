# core/database/user_ai.py
# Per-user daily limits for AI chat questions.

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today
from .vip import is_vip

AI_LIMIT_FREE = 2
AI_LIMIT_VIP = 20


async def get_user_ai_limit(user_id: str) -> int:
    vip = await is_vip(user_id)
    return AI_LIMIT_VIP if vip else AI_LIMIT_FREE


async def get_ai_questions_today(user_id: str) -> int:
    return await get_period_usage(
        user_id,
        "ai_chat_count",
        "ai_chat_date",
        get_tehran_today(),
        cache_service="ai_chat",
    )


async def can_user_ask_ai(user_id: str) -> tuple[bool, int, int]:
    """Returns (allowed, used_today, limit)."""
    limit = await get_user_ai_limit(user_id)
    used = await get_ai_questions_today(user_id)
    return used < limit, used, limit


async def increment_ai_question(user_id: str) -> int:
    return await increment_period_usage(
        user_id,
        "ai_chat_count",
        "ai_chat_date",
        get_tehran_today(),
        monitor_section="ai_chat",
        cache_service="ai_chat",
    )
