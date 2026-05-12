# core/database/settings.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم


async def get_setting(key, default=None):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ) as cursor:
        result = await cursor.fetchone()
        return result[0] if result else default


async def set_setting(key, value):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    await conn.commit()
