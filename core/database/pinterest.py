# core/database/pinterest.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_today


async def get_pinterest_downloads(user_id):
    today = get_tehran_today()
    from services.rate_limiter import get_cached_daily_usage, set_cached_daily_usage
    cached = await get_cached_daily_usage("pinterest", user_id, today)
    if cached is not None:
        return cached

    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT pinterest_count, pinterest_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            count, db_date = result
            actual_count = 0 if db_date != today else (count or 0)
            await set_cached_daily_usage("pinterest", user_id, today, actual_count)
            return actual_count
        await set_cached_daily_usage("pinterest", user_id, today, 0)
        return 0


async def increment_pinterest_downloads(user_id):
    today = get_tehran_today()
    from services.rate_limiter import incr_cached_daily_usage
    await incr_cached_daily_usage("pinterest", user_id, today)

    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT pinterest_count, pinterest_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()

    if result:
        count, db_date = result
        new_count = 1 if db_date != today else (count or 0) + 1
        await conn.execute(
            "UPDATE users SET pinterest_count = ?, pinterest_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    await conn.commit()
    from .monitoring import log_upload_success

    await log_upload_success("pinterest", user_id)
