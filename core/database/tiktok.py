# core/database/tiktok.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_today


async def get_tt_downloads(user_id):
    today = get_tehran_today()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT tt_dl_count, tt_dl_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            return 0 if result[1] != today else result[0]
        return 0


async def increment_tt_downloads(user_id):
    today = get_tehran_today()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT tt_dl_count, tt_dl_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
    if result:
        new_count = 1 if result[1] != today else result[0] + 1
        await conn.execute(
            "UPDATE users SET tt_dl_count = ?, tt_dl_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    await conn.commit()
    from .monitoring import log_upload_success

    await log_upload_success("tiktok", user_id)
