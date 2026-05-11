# core/database/usage.py

import aiosqlite
import sqlite3
from .base import DB_NAME
from .utils import get_tehran_today


async def log_usage(user_id, action):
    today = get_tehran_today()
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute(
                """
                INSERT INTO usage_stats (user_id, action, date, count) 
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, action, date) 
                DO UPDATE SET count = count + 1
            """,
                (user_id, action, today),
            )
            await conn.commit()
    except sqlite3.OperationalError:
        pass


async def get_user_usage_today(user_id, action):
    today = get_tehran_today()
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute(
                "SELECT count FROM usage_stats WHERE user_id = ? AND action = ? AND date = ?",
                (user_id, action, today),
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0
    except sqlite3.OperationalError:
        return 0
