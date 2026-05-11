# core/database/music.py

import aiosqlite
from .base import DB_NAME
from .utils import get_tehran_today


async def get_music_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT music_count, music_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                count, db_date = result
                return 0 if db_date != today else count
            return 0


async def increment_music_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT music_count, music_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()

        if result:
            count, db_date = result
            new_count = 1 if db_date != today else count + 1
            await conn.execute(
                "UPDATE users SET music_count = ?, music_date = ? WHERE user_id = ?",
                (new_count, today, user_id),
            )
        await conn.commit()
