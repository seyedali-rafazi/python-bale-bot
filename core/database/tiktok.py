# core/database/tiktok.py

import aiosqlite
from .base import DB_NAME
from .utils import get_tehran_today


async def get_tt_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT tt_dl_count, tt_dl_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                return 0 if result[1] != today else result[0]
            return 0


async def increment_tt_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
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


async def get_tt_explores(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT tt_exp_count, tt_exp_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                return 0 if result[1] != today else result[0]
            return 0


async def increment_tt_explores(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT tt_exp_count, tt_exp_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
        if result:
            new_count = 1 if result[1] != today else result[0] + 1
            await conn.execute(
                "UPDATE users SET tt_exp_count = ?, tt_exp_date = ? WHERE user_id = ?",
                (new_count, today, user_id),
            )
        await conn.commit()


async def add_tiktok_explore_video(file_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO tiktok_explore (file_id) VALUES (?)", (file_id,)
        )
        await conn.commit()


async def get_random_tiktok_explore_videos(limit=5):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT file_id FROM tiktok_explore ORDER BY RANDOM() LIMIT ?", (limit,)
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def delete_invalid_video_from_db(file_id: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM tiktok_explore WHERE file_id = ?", (file_id,))
        await conn.commit()
