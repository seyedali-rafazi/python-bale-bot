# core/database/youtube.py

import asyncio
import json
import re

from .connection import get_db
from .counters import (
    decrement_period_usage,
    get_period_usage,
    increment_period_usage,
)
from .utils import get_tehran_now_full, get_tehran_today

CHANNELS_PAGE_SIZE = 5
VIDEOS_PAGE_SIZE = 8

PLACEHOLDER_CHANNELS = ("ناشناس", "Unknown", "unknown", "")
PLACEHOLDER_TITLES = ("بدون عنوان", "")

# Only real channel names appear in the archive channel list
# Newest YouTube channel publish date first; never sort by cached_at (bot storage time)
_CHANNEL_VIDEOS_ORDER_SQL = """
    (CASE WHEN uploaded_at IS NOT NULL AND TRIM(uploaded_at) != '' THEN 0 ELSE 1 END),
    uploaded_at DESC,
    id DESC
"""

_CACHE_NEEDS_UPLOAD_DATE_SQL = """
    file_ids IS NOT NULL AND file_ids != '[]'
    AND (uploaded_at IS NULL OR TRIM(uploaded_at) = '')
"""

_CHANNEL_KNOWN_SQL = """
    channel_name IS NOT NULL
    AND TRIM(channel_name) != ''
    AND channel_name NOT IN ('ناشناس', 'Unknown', 'unknown')
"""

# One list entry per YouTube video (not per quality row in youtube_cache)
_YT_GROUP_KEY_SQL = """
    COALESCE(
        NULLIF(TRIM(yt_video_id), ''),
        substr(video_id, 1, 11)
    )
"""

_CACHE_HAS_FILES_SQL = "file_ids IS NOT NULL AND file_ids != '[]'"

_NEEDS_METADATA_SQL = """
    (
        channel_name IS NULL OR channel_name IN ('ناشناس', 'Unknown', 'unknown', '')
        OR title IS NULL OR title IN ('بدون عنوان', '')
        OR yt_video_id IS NULL OR TRIM(yt_video_id) = ''
    )
"""

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


async def _invalidate_archive_summary_cache() -> None:
    from services.cache_service import cache_delete

    await cache_delete("yt_archive:count_global")
    await cache_delete("yt_archive:count_channels")
    await cache_delete("yt_archive:channels_p0")


async def get_yt_downloads(user_id) -> int:
    return await get_period_usage(
        user_id,
        "yt_count",
        "yt_date",
        get_tehran_today(),
        cache_service="youtube",
    )


async def increment_yt_downloads(user_id) -> int:
    return await increment_period_usage(
        user_id,
        "yt_count",
        "yt_date",
        get_tehran_today(),
        monitor_section="youtube",
        cache_service="youtube",
    )


async def decrement_yt_downloads(user_id) -> None:
    await decrement_period_usage(
        user_id,
        "yt_count",
        "yt_date",
        get_tehran_today(),
        cache_service="youtube",
    )


async def get_cached_video(video_id: str) -> list:
    from services.cache_service import cache_get, cache_set

    cache_key = f"yt_video:{video_id}"
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, list):
        return cached

    pool = await get_db()
    raw_file_ids = await pool.fetchval(
        "SELECT file_ids FROM youtube_cache WHERE video_id = $1",
        video_id,
    )
    if raw_file_ids:
        try:
            parsed = json.loads(raw_file_ids)
            await cache_set(cache_key, parsed, ttl_sec=86400 * 7)
            return parsed
        except Exception:
            return []
    return []


async def get_cache_row_metadata(video_id: str) -> dict | None:
    """Return cached metadata columns for video_id without spawning yt-dlp."""
    pool = await get_db()
    row = await pool.fetchrow(
        """
        SELECT title, channel_name, yt_video_id, uploaded_at, format_type
        FROM youtube_cache
        WHERE video_id = $1
        """,
        video_id,
    )
    if not row:
        return None
    return {
        "title": row["title"],
        "uploader": row["channel_name"],
        "channel": row["channel_name"],
        "yt_video_id": row["yt_video_id"],
        "uploaded_at": row["uploaded_at"],
        "format_type": row["format_type"],
    }


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
    pool = await get_db()
    await pool.execute(
        """
        INSERT INTO youtube_cache (
            video_id, file_ids, title, channel_name, yt_video_id,
            format_type, quality, cached_at, uploaded_at, view_count
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0)
        ON CONFLICT(video_id) DO UPDATE SET
            file_ids = EXCLUDED.file_ids,
            title = CASE
                WHEN EXCLUDED.title IS NOT NULL AND TRIM(EXCLUDED.title) != ''
                     AND EXCLUDED.title NOT IN ('بدون عنوان')
                THEN EXCLUDED.title ELSE youtube_cache.title END,
            channel_name = CASE
                WHEN EXCLUDED.channel_name IS NOT NULL AND TRIM(EXCLUDED.channel_name) != ''
                     AND EXCLUDED.channel_name NOT IN ('ناشناس', 'Unknown', 'unknown')
                THEN EXCLUDED.channel_name ELSE youtube_cache.channel_name END,
            yt_video_id = COALESCE(NULLIF(TRIM(EXCLUDED.yt_video_id), ''), youtube_cache.yt_video_id),
            format_type = EXCLUDED.format_type,
            quality = EXCLUDED.quality,
            cached_at = EXCLUDED.cached_at,
            uploaded_at = COALESCE(
                NULLIF(TRIM(EXCLUDED.uploaded_at), ''),
                youtube_cache.uploaded_at
            )
        """,
        cache_key,
        file_ids_json,
        _normalize_title(title),
        _normalize_channel(channel_name),
        yt_video_id or extract_yt_id_from_cache_key(cache_key),
        format_type,
        quality,
        cached_at,
        (uploaded_at or "").strip()[:14] or None,
    )
    from services.cache_service import cache_set

    await cache_set(f"yt_video:{cache_key}", file_ids, ttl_sec=86400 * 7)
    await _invalidate_archive_summary_cache()


async def update_cache_metadata(
    cache_key: str,
    title: str | None,
    channel_name: str | None,
    yt_video_id: str | None,
    uploaded_at: str | None = None,
):
    pool = await get_db()
    await pool.execute(
        """
        UPDATE youtube_cache SET
            title = COALESCE($1, title),
            channel_name = COALESCE($2, channel_name),
            yt_video_id = COALESCE($3, yt_video_id),
            uploaded_at = COALESCE(NULLIF(TRIM($4), ''), uploaded_at)
        WHERE video_id = $5
        """,
        _normalize_title(title),
        _normalize_channel(channel_name),
        yt_video_id,
        (uploaded_at or "").strip()[:14] or None,
        cache_key,
    )


async def count_incomplete_cache_rows() -> int:
    pool = await get_db()
    val = await pool.fetchval(
        f"SELECT COUNT(*) FROM youtube_cache WHERE {_PURGE_INCOMPLETE_SQL}"
    )
    return int(val or 0)


async def purge_incomplete_youtube_cache() -> int:
    """Delete rows without real channel/title (ناشناس, empty, etc.)."""
    pool = await get_db()
    deleted = await pool.fetchval(
        f"""
        WITH deleted AS (
            DELETE FROM youtube_cache
            WHERE {_PURGE_INCOMPLETE_SQL}
            RETURNING 1
        )
        SELECT COUNT(*) FROM deleted
        """
    )
    count = int(deleted or 0)
    if count > 0:
        await _invalidate_archive_summary_cache()
    return count


async def purge_all_youtube_cache() -> int:
    """Wipe entire shared YouTube cache table."""
    pool = await get_db()
    deleted = await pool.fetchval(
        """
        WITH deleted AS (
            DELETE FROM youtube_cache
            RETURNING 1
        )
        SELECT COUNT(*) FROM deleted
        """
    )
    await _invalidate_archive_summary_cache()
    return int(deleted or 0)


async def drop_legacy_user_youtube_archive_table():
    pool = await get_db()
    await pool.execute("DROP TABLE IF EXISTS user_youtube_archive")


async def count_cache_needing_metadata() -> int:
    pool = await get_db()
    val = await pool.fetchval(
        f"""
        SELECT COUNT(*) FROM youtube_cache
        WHERE {_NEEDS_METADATA_SQL} OR ({_CACHE_NEEDS_UPLOAD_DATE_SQL})
        """
    )
    return int(val or 0)


async def get_cache_rows_needing_metadata(limit: int = 50):
    pool = await get_db()
    return await pool.fetch(
        f"""
        SELECT video_id, yt_video_id, title, channel_name, uploaded_at
        FROM youtube_cache
        WHERE {_NEEDS_METADATA_SQL} OR ({_CACHE_NEEDS_UPLOAD_DATE_SQL})
        ORDER BY
            (CASE WHEN uploaded_at IS NOT NULL AND TRIM(uploaded_at) != '' THEN 0 ELSE 1 END),
            uploaded_at DESC,
            id DESC
        LIMIT $1
        """,
        limit,
    )


async def backfill_youtube_cache_metadata(
    batch_size: int = 30,
    max_total: int | None = 500,
    delay_sec: float = 0.4,
) -> dict:
    """Fetch title/channel from YouTube for old cache rows missing metadata."""
    from services.youtube import get_video_info, uploaded_at_from_video_info

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

            uploaded = uploaded_at_from_video_info(info) if info else None
            has_title = bool(info and info.get("title"))
            has_upload_date = bool(uploaded)

            if has_title or has_upload_date:
                await update_cache_metadata(
                    cache_key,
                    info.get("title") if has_title else None,
                    info.get("uploader") if has_title else None,
                    yt_id,
                    uploaded_at=uploaded,
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
    pool = await get_db()
    val = await pool.fetchval(
        """
        SELECT COUNT(*) FROM youtube_cache
        WHERE (uploaded_at IS NULL OR TRIM(uploaded_at) = '')
          AND yt_video_id IS NOT NULL AND TRIM(yt_video_id) != ''
        """
    )
    return int(val or 0)


async def get_cache_rows_missing_upload_date(limit: int = 50):
    pool = await get_db()
    return await pool.fetch(
        """
        SELECT video_id, yt_video_id
        FROM youtube_cache
        WHERE (uploaded_at IS NULL OR TRIM(uploaded_at) = '')
          AND yt_video_id IS NOT NULL AND TRIM(yt_video_id) != ''
        ORDER BY id DESC
        LIMIT $1
        """,
        limit,
    )


async def backfill_upload_dates_for_cache_rows(
    rows, delay_sec: float = 0.35
) -> int:
    """Fill missing YouTube publish dates for rows shown in the archive UI."""
    from services.youtube import get_video_info, uploaded_at_from_video_info

    fixed = 0
    for row in rows:
        try:
            existing = row["uploaded_at"]
        except (KeyError, IndexError, TypeError):
            existing = None
        if existing and str(existing).strip():
            continue

        cache_key = row["video_id"]
        try:
            yt_id = (row["yt_video_id"] or "").strip() or extract_yt_id_from_cache_key(
                cache_key
            )
        except (KeyError, IndexError, TypeError):
            yt_id = extract_yt_id_from_cache_key(cache_key)

        if not yt_id:
            continue

        url = f"https://www.youtube.com/watch?v={yt_id}"
        try:
            info = await asyncio.to_thread(get_video_info, url)
        except Exception:
            info = None

        uploaded = uploaded_at_from_video_info(info) if info else None
        if not uploaded:
            continue

        await update_cache_metadata(
            cache_key, None, None, yt_id, uploaded_at=uploaded
        )
        fixed += 1
        if delay_sec > 0:
            await asyncio.sleep(delay_sec)

    return fixed


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
    from services.cache_service import cache_get, cache_set

    cached = await cache_get("yt_archive:count_global")
    if isinstance(cached, int):
        return cached

    pool = await get_db()
    val = await pool.fetchval(
        "SELECT COUNT(*) FROM youtube_cache WHERE file_ids IS NOT NULL AND file_ids != '[]'"
    )
    count = int(val or 0)
    await cache_set("yt_archive:count_global", count, ttl_sec=60)
    return count


async def get_global_channels_page(offset: int = 0, limit: int = CHANNELS_PAGE_SIZE):
    from services.cache_service import cache_get, cache_set

    cache_key = "yt_archive:channels_p0" if offset == 0 and limit == CHANNELS_PAGE_SIZE else None
    if cache_key:
        cached = await cache_get(cache_key)
        if isinstance(cached, list):
            return cached

    pool = await get_db()
    rows = await pool.fetch(
        f"""
        SELECT channel_name, COUNT(DISTINCT {_YT_GROUP_KEY_SQL}) AS video_count
        FROM youtube_cache
        WHERE {_CHANNEL_KNOWN_SQL}
          AND {_CACHE_HAS_FILES_SQL}
        GROUP BY channel_name
        ORDER BY video_count DESC, channel_name ASC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    if cache_key:
        serialized = [
            {"channel_name": r["channel_name"], "video_count": int(r["video_count"])}
            for r in rows
        ]
        await cache_set(cache_key, serialized, ttl_sec=60)
        return serialized
    return rows


async def count_global_channels() -> int:
    from services.cache_service import cache_get, cache_set

    cached = await cache_get("yt_archive:count_channels")
    if isinstance(cached, int):
        return cached

    pool = await get_db()
    val = await pool.fetchval(
        f"""
        SELECT COUNT(DISTINCT channel_name)
        FROM youtube_cache
        WHERE {_CHANNEL_KNOWN_SQL}
        """
    )
    count = int(val or 0)
    await cache_set("yt_archive:count_channels", count, ttl_sec=60)
    return count


async def get_global_channel_videos_page(
    channel_name: str, offset: int = 0, limit: int = VIDEOS_PAGE_SIZE
):
    """One row per YouTube video (newest cache row per yt_video_id)."""
    pool = await get_db()
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, file_ids,
               format_type, quality, cached_at, uploaded_at, channel_name
        FROM youtube_cache
        WHERE channel_name = $1
          AND {_CACHE_HAS_FILES_SQL}
          AND id IN (
            SELECT MAX(id)
            FROM youtube_cache
            WHERE channel_name = $1
              AND {_CACHE_HAS_FILES_SQL}
            GROUP BY {_YT_GROUP_KEY_SQL}
          )
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT $2 OFFSET $3
        """,
        channel_name,
        limit,
        offset,
    )


async def count_global_channel_videos(channel_name: str) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        f"""
        SELECT COUNT(*) FROM (
            SELECT 1
            FROM youtube_cache
            WHERE channel_name = $1
              AND {_CACHE_HAS_FILES_SQL}
            GROUP BY {_YT_GROUP_KEY_SQL}
        ) AS sub
        """,
        channel_name,
    )
    return int(val or 0)


async def get_cache_variants_for_video(
    channel_name: str, yt_video_id: str
) -> list:
    """All cached qualities/formats for the same YouTube video in a channel."""
    pool = await get_db()
    yt_video_id = (yt_video_id or "").strip()
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, quality, cached_at, uploaded_at
        FROM youtube_cache
        WHERE channel_name = $1
          AND {_YT_GROUP_KEY_SQL} = $2
          AND {_CACHE_HAS_FILES_SQL}
        ORDER BY
            CASE WHEN format_type LIKE '%audio%' THEN 1 ELSE 0 END,
            CASE WHEN quality ~ '^[0-9]+$' THEN quality::INTEGER ELSE 0 END DESC,
            id DESC
        """,
        channel_name,
        yt_video_id,
    )


def archive_row_yt_id(row) -> str:
    try:
        yt_id = row["yt_video_id"]
    except (KeyError, TypeError):
        yt_id = None
    if yt_id and str(yt_id).strip():
        return str(yt_id).strip()
    try:
        vid = row["video_id"]
    except (KeyError, TypeError):
        vid = ""
    return extract_yt_id_from_cache_key(vid or "") or ""


def dedupe_archive_rows(rows: list) -> list:
    """Keep one representative row per YouTube video (newest upload date)."""
    best: dict[str, tuple] = {}
    order: list[str] = []
    for row in rows:
        key = archive_row_yt_id(row) or f"row_{row['id']}"
        uploaded = ""
        try:
            uploaded = row["uploaded_at"] or ""
        except (KeyError, TypeError):
            pass
        if key not in best or (uploaded or "") > (best[key][1] or ""):
            best[key] = (row, uploaded)
            if key not in order:
                order.append(key)
    return [best[k][0] for k in order]


async def get_cache_entry_by_rowid(rowid: int):
    pool = await get_db()
    return await pool.fetchrow(
        """
        SELECT id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, quality, cached_at
        FROM youtube_cache WHERE id = $1
        """,
        int(rowid),
    )


async def search_global_cache_by_title(query: str, limit: int = 15):
    pool = await get_db()
    pattern = f"%{query.strip()}%"
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, cached_at, uploaded_at
        FROM youtube_cache
        WHERE title ILIKE $1
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT $2
        """,
        pattern,
        limit,
    )


async def search_global_cache_by_channel(query: str, limit: int = 15):
    pool = await get_db()
    pattern = f"%{query.strip()}%"
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, channel_name,
               file_ids, format_type, cached_at, uploaded_at
        FROM youtube_cache
        WHERE channel_name ILIKE $1
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT $2
        """,
        pattern,
        limit,
    )


async def increment_yt_video_view(video_id: str):
    pool = await get_db()
    await pool.execute(
        "UPDATE youtube_cache SET view_count = view_count + 1 WHERE video_id = $1",
        video_id,
    )


async def get_top_cached_videos(limit: int = 10):
    pool = await get_db()
    return await pool.fetch(
        "SELECT video_id, file_ids, view_count FROM youtube_cache ORDER BY view_count DESC LIMIT $1",
        limit,
    )
