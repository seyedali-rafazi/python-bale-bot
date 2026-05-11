# core/database/settings.py

import aiosqlite
from .base import DB_NAME


async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else default


async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        await conn.commit()
