# core/database/youtube.py

import json
import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
import sqlite3  # این خط را نگه می‌داریم فقط اگر لازم باشد، اما ترجیحا `aiosqlite.Row` استفاده شود
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_today


async def get_yt_downloads(user_id):
    today = get_tehran_today()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            return 0 if result[1] != today else result[0]
        return 0


async def increment_yt_downloads(user_id):
    today = get_tehran_today()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
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
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
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
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT file_ids FROM youtube_cache WHERE video_id = ?", (video_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result and result[0]:
            return json.loads(result[0])
        return []


async def save_cached_video(video_id: str, file_ids: list):
    file_ids_json = json.dumps(file_ids)
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        "INSERT OR REPLACE INTO youtube_cache (video_id, file_ids) VALUES (?, ?)",
        (video_id, file_ids_json),
    )
    await conn.commit()


async def increment_yt_video_view(video_id: str):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        "UPDATE youtube_cache SET view_count = view_count + 1 WHERE video_id = ?",
        (video_id,),
    )
    await conn.commit()


async def get_top_cached_videos(limit=10):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    # conn.row_factory = sqlite3.Row # این خط حذف شد. row_factory در get_db() تنظیم شده و باید کافی باشد.
    async with conn.execute(
        "SELECT video_id, file_ids, view_count FROM youtube_cache ORDER BY view_count DESC LIMIT ?",
        (limit,),
    ) as cursor:
        # aiosqlite.Row به شما امکان دسترسی دیکشنری مانند می‌دهد، نیازی به dict(row) نیست
        # مگر اینکه واقعا شی dict خالص مورد نیاز باشد.
        # می‌توانید به جای dict(row) از row برای دسترسی به مقادیر استفاده کنید.
        # اگر dict() ضروری است، ممکن است نیاز به تبدیل صریح داشته باشید:
        # return [{col: row[col] for col in row.keys()} for row in await cursor.fetchall()]
        # اما برای سادگی، فعلا row مستقیم را برمی‌گردانیم، چون رفتار آن مشابه dict است.
        return await cursor.fetchall()
