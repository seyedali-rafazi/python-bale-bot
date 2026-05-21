# core/database/youtube.py

import asyncio
import json
import re
import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
import sqlite3  # این خط را نگه می‌داریم فقط اگر لازم باشد، اما ترجیحا `aiosqlite.Row` استفاده شود
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_today, get_tehran_now_full

CHANNELS_PAGE_SIZE = 5
VIDEOS_PAGE_SIZE = 8

PLACEHOLDER_CHANNELS = ("ناشناس", "Unknown", "unknown", "")
PLACEHOLDER_TITLES = ("بدون عنوان", "")

# Only real channel names appear in the archive channel list
# Newest YouTube upload first; rows without uploaded_at fall back to cached_at
_CHANNEL_VIDEOS_ORDER_SQL = """
    (CASE WHEN uploaded_at IS NOT NULL AND TRIM(uploaded_at) != '' THEN 0 ELSE 1 END),
    uploaded_at DESC,
    cached_at DESC
"""

_CHANNEL_KNOWN_SQL = """
    channel_name IS NOT NULL
    AND TRIM(channel_name) != ''
    AND channel_name NOT IN ('ناشناس', 'Unknown', 'unknown')
"""

_NEEDS_METADATA_SQL = """
    (
        channel_name IS NULL OR channel_name IN ('ناشناس', 'Unknown', 'unknown', '')
        OR title IS NULL OR title IN ('بدون عنوان', '')
        OR yt_video_id IS NULL OR TRIM(yt_video_id) = ''
    )
"""

# Rows removed by cleanup (incomplete / ناشناس legacy data)
_PURGE_INCOMPLETE_SQL = _NEEDS_METADATA_SQL

# Rows removed by cleanup (incomplete / ناشناس legacy data)
_PURGE_INCOMPLETE_SQL = _NEEDS_METADATA_SQL


def extract_yt_id_from_cache_key(cache_key: str) -> str | None:
    match = re.match(r"^([0-9A-Za-z_-]{11})", cache_key or "")
    return match.group(1) if match else None


def _normalize_title(title: str | None) -> str | None:
    if not title or title.strip() in PLACEHOLDER_TITLES:
        return None
    return title.strip()[:500]


def _normalize_channel(channel: str | None) -> str | None:
    if not channel or channel.strip() in PLACEHOLDER_CHANNELS:
        return None
    return channel.strip()[:200]


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
    uploaded_at: str | None = None,
):
    file_ids_json = json.dumps(file_ids)
    cached_at = get_tehran_now_full()
    conn = await get_db()
    await conn.execute(
        """
        INSERT INTO youtube_cache (
            video_id, file_ids, title, channel_name, yt_video_id,
            format_type, quality, cached_at, uploaded_at, view_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(video_id) DO UPDATE SET
            file_ids = excluded.file_ids,
            title = CASE
                WHEN excluded.title IS NOT NULL AND TRIM(excluded.title) != ''
                     AND excluded.title NOT IN ('بدون عنوان')
                THEN excluded.title ELSE youtube_cache.title END,
            channel_name = CASE
                WHEN excluded.channel_name IS NOT NULL AND TRIM(excluded.channel_name) != ''
                     AND excluded.channel_name NOT IN ('ناشناس', 'Unknown', 'unknown')
                THEN excluded.channel_name ELSE youtube_cache.channel_name END,
            yt_video_id = COALESCE(NULLIF(TRIM(excluded.yt_video_id), ''), youtube_cache.yt_video_id),
            format_type = excluded.format_type,
            quality = excluded.quality,
            cached_at = excluded.cached_at,
            uploaded_at = COALESCE(
                NULLIF(TRIM(excluded.uploaded_at), ''),
                youtube_cache.uploaded_at
            )
        """,
        (
            cache_key,
            file_ids_json,
            _normalize_title(title),
            _normalize_channel(channel_name),
            yt_video_id or extract_yt_id_from_cache_key(cache_key),
            format_type,
            quality,
            cached_at,
            (uploaded_at or "").strip()[:8] or None,
        ),
    )
    await conn.commit()


async def update_cache_metadata(
    cache_key: str,
    title: str | None,
    channel_name: str | None,
    yt_video_id: str | None,
    uploaded_at: str | None = None,
):
    conn = await get_db()
    await conn.execute(
        """
        UPDATE youtube_cache SET
            title = COALESCE(?, title),
            channel_name = COALESCE(?, channel_name),
            yt_video_id = COALESCE(?, yt_video_id),
            uploaded_at = COALESCE(NULLIF(TRIM(?), ''), uploaded_at)
        WHERE video_id = ?
        """,
        (
            _normalize_title(title),
            _normalize_channel(channel_name),
            yt_video_id,
            (uploaded_at or "").strip()[:8] or None,
            cache_key,
        ),
    )
    await conn.commit()


async def count_incomplete_cache_rows() -> int:
    conn = await get_db()
    async with conn.execute(
        f"SELECT COUNT(*) FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}"
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def purge_incomplete_youtube_cache() -> int:
    """Delete rows without real channel/title (ناشناس, empty, etc.)."""
    conn = await get_db()
    async with conn.execute(
        f"SELECT COUNT(*) FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}"
    ) as cursor:
        row = await cursor.fetchone()
        to_delete = row[0] if row else 0
    if to_delete == 0:
        return 0
    await conn.execute(f"DELETE FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}")
    await conn.commit()
    return to_delete


async def purge_all_youtube_cache() -> int:
    """Wipe entire shared YouTube cache table."""
    conn = await get_db()
    async with conn.execute("SELECT COUNT(*) FROM youtube_cache") as cursor:
        row = await cursor.fetchone()
        total = row[0] if row else 0
    await conn.execute("DELETE FROM youtube_cache")
    await conn.commit()
    return total


async def drop_legacy_user_youtube_archive_table():
    conn = await get_db()
    await conn.execute("DROP TABLE IF EXISTS user_youtube_archive")
    await conn.commit()


async def count_incomplete_cache_rows() -> int:
    conn = await get_db()
    async with conn.execute(
        f"SELECT COUNT(*) FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}"
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def purge_incomplete_youtube_cache() -> int:
    """Delete rows without real channel/title (ناشناس, empty, etc.)."""
    conn = await get_db()
    async with conn.execute(
        f"SELECT COUNT(*) FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}"
    ) as cursor:
        row = await cursor.fetchone()
        to_delete = row[0] if row else 0
    if to_delete == 0:
        return 0
    await conn.execute(f"DELETE FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}")
    await conn.commit()
    return to_delete


async def purge_all_youtube_cache() -> int:
    """Wipe entire shared YouTube cache table."""
    conn = await get_db()
    async with conn.execute("SELECT COUNT(*) FROM youtube_cache") as cursor:
        row = await cursor.fetchone()
        total = row[0] if row else 0
    await conn.execute("DELETE FROM youtube_cache")
    await conn.commit()
    return total


async def drop_legacy_user_youtube_archive_table():
    conn = await get_db()
    await conn.execute("DROP TABLE IF EXISTS user_youtube_archive")
    await conn.commit()


async def count_cache_needing_metadata() -> int:
    conn = await get_db()
    async with conn.execute(
        f"SELECT COUNT(*) FROM youtube_cache WHERE {_NEEDS_METADATA_SQL}"
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_cache_rows_needing_metadata(limit: int = 50):
    conn = await get_db()
    async with conn.execute(
        f"""
        SELECT video_id, yt_video_id, title, channel_name
        FROM youtube_cache
        WHERE {_NEEDS_METADATA_SQL}
        ORDER BY COALESCE(cached_at, '') DESC
        LIMIT ?
        """,
        (limit,),
    ) as cursor:
        return await cursor.fetchall()


async def backfill_youtube_cache_metadata(
    batch_size: int = 30,
    max_total: int | None = 500,
    delay_sec: float = 0.4,
) -> dict:
    """Fetch title/channel from YouTube for old cache rows missing metadata."""
    from services.youtube import get_video_info

    fixed = 0
    failed = 0
    processed = 0

    while True:
        rows = await get_cache_rows_needing_metadata(batch_size)
        if not rows:
            break

        for row in rows:
            if max_total is not None and processed >= max_total:
                return {"fixed": fixed, "failed": failed, "processed": processed}

            cache_key = row["video_id"]
            yt_id = (row["yt_video_id"] or "").strip() or extract_yt_id_from_cache_key(
                cache_key
            )
            processed += 1

            if not yt_id:
                failed += 1
                continue

            url = f"https://www.youtube.com/watch?v={yt_id}"
            try:
                info = await asyncio.to_thread(get_video_info, url)
            except Exception:
                info = None

            if info and info.get("title"):
                from services.youtube import uploaded_at_from_video_info

                await update_cache_metadata(
                    cache_key,
                    info.get("title"),
                    info.get("uploader"),
                    yt_id,
                    uploaded_at=uploaded_at_from_video_info(info),
                )
                fixed += 1
            else:
                failed += 1

            if delay_sec > 0:
                await asyncio.sleep(delay_sec)

        if len(rows) < batch_size:
            break

    return {"fixed": fixed, "failed": failed, "processed": processed}


async def count_cache_missing_upload_date() -> int:
    conn = await get_db()
    async with conn.execute(
        """
        SELECT COUNT(*) FROM youtube_cache
        WHERE (uploaded_at IS NULL OR TRIM(uploaded_at) = '')
          AND yt_video_id IS NOT NULL AND TRIM(yt_video_id) != ''
        """
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_cache_rows_missing_upload_date(limit: int = 50):
    conn = await get_db()
    async with conn.execute(
        """
        SELECT video_id, yt_video_id
        FROM youtube_cache
        WHERE (uploaded_at IS NULL OR TRIM(uploaded_at) = '')
          AND yt_video_id IS NOT NULL AND TRIM(yt_video_id) != ''
        ORDER BY cached_at DESC
        LIMIT ?
        """,
        (limit,),
    ) as cursor:
        return await cursor.fetchall()


async def backfill_cache_upload_dates(
    batch_size: int = 40,
    max_total: int | None = 2000,
    delay_sec: float = 0.35,
) -> dict:
    from services.youtube import get_video_info, uploaded_at_from_video_info

    fixed = 0
    failed = 0
    processed = 0

    while True:
        rows = await get_cache_rows_missing_upload_date(batch_size)
        if not rows:
            break

        for row in rows:
            if max_total is not None and processed >= max_total:
                return {"fixed": fixed, "failed": failed, "processed": processed}

            cache_key = row["video_id"]
            yt_id = (row["yt_video_id"] or "").strip() or extract_yt_id_from_cache_key(
                cache_key
            )
            processed += 1
            if not yt_id:
                failed += 1
                continue

            url = f"https://www.youtube.com/watch?v={yt_id}"
            try:
                info = await asyncio.to_thread(get_video_info, url)
            except Exception:
                info = None

            uploaded = uploaded_at_from_video_info(info)
            if uploaded:
                await update_cache_metadata(
                    cache_key, None, None, yt_id, uploaded_at=uploaded
                )
                fixed += 1
            else:
                failed += 1

            if delay_sec > 0:
                await asyncio.sleep(delay_sec)

        if len(rows) < batch_size:
            break

    return {"fixed": fixed, "failed": failed, "processed": processed}


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
        f"""
        SELECT channel_name, COUNT(*) AS video_count
        FROM youtube_cache
        WHERE {_CHANNEL_KNOWN_SQL}
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
        f"""
        SELECT COUNT(DISTINCT channel_name)
        FROM youtube_cache
        WHERE {_CHANNEL_KNOWN_SQL}
        """
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_global_channel_videos_page(
    channel_name: str, offset: int = 0, limit: int = VIDEOS_PAGE_SIZE
):
    conn = await get_db()
    async with conn.execute(
        f"""
        SELECT rowid AS id, video_id, yt_video_id, title, file_ids,
               format_type, quality, cached_at, uploaded_at
        FROM youtube_cache
        WHERE channel_name = ?
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
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
        f"""
        SELECT rowid AS id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, cached_at
        FROM youtube_cache
        WHERE title LIKE ?
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT ?
        """,
        (pattern, limit),
    ) as cursor:
        return await cursor.fetchall()


async def search_global_cache_by_channel(query: str, limit: int = 15):
    conn = await get_db()
    pattern = f"%{query.strip()}%"
    async with conn.execute(
        f"""
        SELECT rowid AS id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, cached_at
        FROM youtube_cache
        WHERE channel_name LIKE ?
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
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
