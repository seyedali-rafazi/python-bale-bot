# core/database/telegram.py

from .connection import get_db
from .utils import get_tehran_today


async def get_tg_downloads(user_id: str) -> int:
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT tg_count, tg_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            count, db_date = result
            return count if db_date == today else 0
        return 0


async def increment_tg_downloads(user_id: str) -> None:
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT tg_count, tg_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()

    if result:
        count, db_date = result
        new_count = 1 if db_date != today else count + 1
        await conn.execute(
            "UPDATE users SET tg_count = ?, tg_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    await conn.commit()
    from .monitoring import log_upload_success

    await log_upload_success("telegram", user_id)
