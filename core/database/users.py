# core/database/users.py

import aiosqlite
from .base import DB_NAME
from .utils import get_tehran_now_full, get_tehran_today


async def add_user(user_id, username):
    join_date = get_tehran_now_full()
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, is_vip, join_date, yt_count, yt_date, pinterest_count, pinterest_date) 
            VALUES (?, ?, 0, ?, 0, ?, 0, ?)
        """,
            (user_id, username, join_date, today, today),
        )
        await conn.commit()


async def set_vip(user_id, status: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "UPDATE users SET is_vip = ? WHERE user_id = ?", (status, user_id)
        )
        await conn.commit()


async def get_user_info(user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT username, is_vip, join_date, vip_expire_date FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            return await cursor.fetchone()


async def get_total_users():
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            return (await cursor.fetchone())[0]


async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM users") as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def reset_user_limits(user_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            """
            UPDATE users 
            SET yt_count = 0, music_count = 0, pinterest_count = 0, tt_dl_count = 0, tt_exp_count = 0
            WHERE user_id = ?
        """,
            (user_id,),
        )
        await conn.commit()
