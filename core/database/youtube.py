# core/database/youtube.py

import json
import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
import sqlite3  # این خط را نگه می‌داریم فقط اگر لازم باشد، اما ترجیحا `aiosqlite.Row` استفاده شود
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_today, get_tehran_now_full

CHANNELS_PAGE_SIZE = 5
VIDEOS_PAGE_SIZE = 8


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


async def save_cached_video(
    cache_key: str,
    file_ids: list,
    title: str | None = None,
    channel_name: str | None = None,
    yt_video_id: str | None = None,
    format_type: str = "video_zip",
    quality: str = "480",
):
    file_ids_json = json.dumps(file_ids)
    cached_at = get_tehran_now_full()
    conn = await get_db()
    await conn.execute(
        """
        INSERT INTO youtube_cache (
            video_id, file_ids, title, channel_name, yt_video_id,
            format_type, quality, cached_at, view_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(video_id) DO UPDATE SET
            file_ids = excluded.file_ids,
            title = COALESCE(excluded.title, youtube_cache.title),
            channel_name = COALESCE(excluded.channel_name, youtube_cache.channel_name),
            yt_video_id = COALESCE(excluded.yt_video_id, youtube_cache.yt_video_id),
            format_type = excluded.format_type,
            quality = excluded.quality,
            cached_at = excluded.cached_at
        """,
        (
            cache_key,
            file_ids_json,
            (title or "بدون عنوان")[:500],
            (channel_name or "ناشناس")[:200],
            yt_video_id,
            format_type,
            quality,
            cached_at,
        ),
    )
    await conn.commit()


async def count_global_cache() -> int:
    conn = await get_db()
    async with conn.execute(
        "SELECT COUNT(*) FROM youtube_cache WHERE file_ids IS NOT NULL AND file_ids != '[]'"
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_global_channels_page(offset: int = 0, limit: int = CHANNELS_PAGE_SIZE):
    conn = await get_db()
    async with conn.execute(
        """
        SELECT channel_name, COUNT(*) AS video_count
        FROM youtube_cache
        WHERE channel_name IS NOT NULL AND channel_name != ''
        GROUP BY channel_name
        ORDER BY video_count DESC, channel_name ASC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ) as cursor:
        return await cursor.fetchall()


async def count_global_channels() -> int:
    conn = await get_db()
    async with conn.execute(
        """
        SELECT COUNT(DISTINCT channel_name)
        FROM youtube_cache
        WHERE channel_name IS NOT NULL AND channel_name != ''
        """
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_global_channel_videos_page(
    channel_name: str, offset: int = 0, limit: int = VIDEOS_PAGE_SIZE
):
    conn = await get_db()
    async with conn.execute(
        """
        SELECT rowid AS id, video_id, yt_video_id, title, file_ids,
               format_type, quality, cached_at
        FROM youtube_cache
        WHERE channel_name = ?
        ORDER BY cached_at DESC
        LIMIT ? OFFSET ?
        """,
        (channel_name, limit, offset),
    ) as cursor:
        return await cursor.fetchall()


async def count_global_channel_videos(channel_name: str) -> int:
    conn = await get_db()
    async with conn.execute(
        "SELECT COUNT(*) FROM youtube_cache WHERE channel_name = ?",
        (channel_name,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_cache_entry_by_rowid(rowid: int):
    conn = await get_db()
    async with conn.execute(
        """
        SELECT rowid AS id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, quality, cached_at
        FROM youtube_cache WHERE rowid = ?
        """,
        (rowid,),
    ) as cursor:
        return await cursor.fetchone()


async def search_global_cache_by_title(query: str, limit: int = 15):
    conn = await get_db()
    pattern = f"%{query.strip()}%"
    async with conn.execute(
        """
        SELECT rowid AS id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, cached_at
        FROM youtube_cache
        WHERE title LIKE ?
        ORDER BY cached_at DESC
        LIMIT ?
        """,
        (pattern, limit),
    ) as cursor:
        return await cursor.fetchall()


async def search_global_cache_by_channel(query: str, limit: int = 15):
    conn = await get_db()
    pattern = f"%{query.strip()}%"
    async with conn.execute(
        """
        SELECT rowid AS id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, cached_at
        FROM youtube_cache
        WHERE channel_name LIKE ?
        ORDER BY cached_at DESC
        LIMIT ?
        """,
        (pattern, limit),
    ) as cursor:
        return await cursor.fetchall()


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
