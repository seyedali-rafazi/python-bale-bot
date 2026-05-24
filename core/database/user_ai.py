# core/database/user_ai.py
# Per-user daily limits for AI chat questions.

from .connection import get_db
from .utils import get_tehran_today
from .vip import is_vip

AI_LIMIT_FREE = 2
AI_LIMIT_VIP = 20


async def get_user_ai_limit(user_id: str) -> int:
    vip = await is_vip(user_id)
    return AI_LIMIT_VIP if vip == 1 else AI_LIMIT_FREE


async def get_ai_questions_today(user_id: str) -> int:
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT ai_chat_count, ai_chat_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["ai_chat_date"] == today:
            return row["ai_chat_count"] or 0
        return 0


async def can_user_ask_ai(user_id: str) -> tuple[bool, int, int]:
    """Returns (allowed, used_today, limit)."""
    limit = await get_user_ai_limit(user_id)
    used = await get_ai_questions_today(user_id)
    return used < limit, used, limit


async def increment_ai_question(user_id: str):
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT ai_chat_count, ai_chat_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        count = 1 if row["ai_chat_date"] != today else (row["ai_chat_count"] or 0) + 1
        await conn.execute(
            "UPDATE users SET ai_chat_count = ?, ai_chat_date = ? WHERE user_id = ?",
            (count, today, user_id),
        )
    await conn.commit()
