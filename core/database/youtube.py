# core/database/youtube.py

import json
import aiosqlite
import sqlite3
from .base import DB_NAME
from .utils import get_tehran_today


async def get_yt_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result:
                return 0 if result[1] != today else result[0]
            return 0


async def increment_yt_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
        if result:
            new_count = 1 if result[1] != today else result[0] + 1
            await conn.execute(
                "UPDATE users SET yt_count = ?, yt_date = ? WHERE user_id = ?",
                (new_count, today, user_id),
            )
        await conn.commit()


async def decrement_yt_downloads(user_id):
    today = get_tehran_today()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
        if result:
            if result[1] == today and result[0] > 0:
                await conn.execute(
                    "UPDATE users SET yt_count = ? WHERE user_id = ?",
                    (result[0] - 1, user_id),
                )
        await conn.commit()


async def get_cached_video(video_id: str) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT file_ids FROM youtube_cache WHERE video_id = ?", (video_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return []


async def save_cached_video(video_id: str, file_ids: list):
    file_ids_json = json.dumps(file_ids)
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO youtube_cache (video_id, file_ids) VALUES (?, ?)",
            (video_id, file_ids_json),
        )
        await conn.commit()


async def increment_yt_video_view(video_id: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "UPDATE youtube_cache SET view_count = view_count + 1 WHERE video_id = ?",
            (video_id,),
        )
        await conn.commit()


async def get_top_cached_videos(limit=10):
    async with aiosqlite.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        async with conn.execute(
            "SELECT video_id, file_ids, view_count FROM youtube_cache ORDER BY view_count DESC LIMIT ?",
            (limit,),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]
