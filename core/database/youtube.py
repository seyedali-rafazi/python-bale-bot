# core/database/youtube.py

import asyncio
import json
import re
import time

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


_archive_channels_gen = 0


async def _invalidate_archive_summary_cache(*, include_top: bool = True) -> None:
    global _archive_channels_gen
    _archive_channels_gen += 1
    from services.cache_service import cache_delete_many, cache_set

    keys = [
        "yt_archive:count_global",
        "yt_archive:count_channels",
        "yt_archive:channels_all",
    ]
    if include_top:
        keys.extend(["yt_archive:top:4", "yt_archive:top:10"])
    await cache_delete_many(keys)
    await cache_set("yt_archive:channels_ver", str(int(time.time() * 1000)), ttl_sec=86400)


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
    # Short negative cache avoids repeated DB misses for uncached videos (overwritten on save_cached_video)
    await cache_set(cache_key, [], ttl_sec=60)
    return []


async def get_cache_row_metadata(video_id: str) -> dict | None:
    """Return cached metadata columns for video_id without spawning yt-dlp."""
    from services.cache_service import cache_get, cache_set

    meta_key = f"yt_meta:{video_id}"
    cached = await cache_get(meta_key)
    if isinstance(cached, dict):
        if cached.get("_missing"):
            return None
        if "format_type" in cached:
            return cached

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
        await cache_set(meta_key, {"_missing": True}, ttl_sec=60)
        return None
    meta = {
        "title": row["title"],
        "uploader": row["channel_name"],
        "channel": row["channel_name"],
        "yt_video_id": row["yt_video_id"],
        "uploaded_at": row["uploaded_at"],
        "format_type": row["format_type"],
    }
    await cache_set(meta_key, meta, ttl_sec=86400 * 7)
    return meta


async def get_cached_video_with_meta(video_id: str) -> tuple[list, dict | None]:
    """Fetch both file_ids list and row metadata in one DB round-trip on cache miss."""
    from services.cache_service import cache_get_many, cache_set, cache_set_many

    video_key = f"yt_video:{video_id}"
    meta_key = f"yt_meta:{video_id}"
    cache_hits = await cache_get_many([video_key, meta_key])
    cached_files = cache_hits.get(video_key)
    cached_meta = cache_hits.get(meta_key)

    if isinstance(cached_files, list):
        if not cached_files:
            return [], None
        if isinstance(cached_meta, dict) and not cached_meta.get("_missing") and "format_type" in cached_meta:
            return cached_files, cached_meta
        # Files cached, only metadata missed
        meta = await get_cache_row_metadata(video_id)
        return cached_files, meta

    pool = await get_db()
    row = await pool.fetchrow(
        """
        SELECT file_ids, title, channel_name, yt_video_id, uploaded_at, format_type
        FROM youtube_cache
        WHERE video_id = $1
        """,
        video_id,
    )
    if not row or not row["file_ids"]:
        await cache_set_many(
            {video_key: [], meta_key: {"_missing": True}},
            ttl_sec=60,
        )
        return [], None

    try:
        parsed = json.loads(row["file_ids"])
    except Exception:
        return [], None

    if not parsed:
        await cache_set(video_key, [], ttl_sec=60)
        return [], None

    meta = {
        "title": row["title"],
        "uploader": row["channel_name"],
        "channel": row["channel_name"],
        "yt_video_id": row["yt_video_id"],
        "uploaded_at": row["uploaded_at"],
        "format_type": row["format_type"],
    }
    await cache_set_many(
        {video_key: parsed, meta_key: meta},
        ttl_sec=86400 * 7,
    )
    return parsed, meta


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
    from services.cache_service import cache_delete, cache_set

    norm_title = _normalize_title(title)
    norm_channel = _normalize_channel(channel_name)
    norm_yt_id = yt_video_id or extract_yt_id_from_cache_key(cache_key)
    norm_uploaded = (uploaded_at or "").strip()[:14] or None
    tasks = [cache_set(f"yt_video:{cache_key}", file_ids, ttl_sec=86400 * 7)]
    if norm_title and norm_channel and norm_uploaded:
        tasks.append(
            cache_set(
                f"yt_meta:{cache_key}",
                {
                    "title": norm_title,
                    "uploader": norm_channel,
                    "channel": norm_channel,
                    "yt_video_id": norm_yt_id,
                    "uploaded_at": norm_uploaded,
                    "format_type": format_type,
                },
                ttl_sec=86400 * 7,
            )
        )
    else:
        tasks.append(cache_delete(f"yt_meta:{cache_key}"))
    await asyncio.gather(*tasks)
    await _invalidate_archive_summary_cache(include_top=False)


async def update_cache_metadata(
    cache_key: str,
    title: str | None,
    channel_name: str | None,
    yt_video_id: str | None,
    uploaded_at: str | None = None,
    *,
    invalidate_summary: bool = True,
):
    norm_title = _normalize_title(title)
    norm_channel = _normalize_channel(channel_name)
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
        norm_title,
        norm_channel,
        yt_video_id,
        (uploaded_at or "").strip()[:14] or None,
        cache_key,
    )
    from services.cache_service import cache_delete_many

    await cache_delete_many([f"yt_video:{cache_key}", f"yt_meta:{cache_key}"])
    if invalidate_summary and (norm_title or norm_channel):
        await _invalidate_archive_summary_cache()


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


async def _batch_update_cache_metadata(
    updates: list[tuple[str, str | None, str | None, str | None, str | None]],
    *,
    invalidate_summary: bool = True,
) -> None:
    """Batch-update youtube_cache metadata rows in a single DB transaction + Redis pipeline."""
    if not updates:
        return
    records = []
    cache_keys = []
    has_summary_change = False
    for cache_key, title, channel_name, yt_video_id, uploaded_at in updates:
        norm_title = _normalize_title(title)
        norm_channel = _normalize_channel(channel_name)
        norm_uploaded = (uploaded_at or "").strip()[:14] or None
        if norm_title or norm_channel:
            has_summary_change = True
        records.append((norm_title, norm_channel, yt_video_id, norm_uploaded, cache_key))
        cache_keys.append(f"yt_video:{cache_key}")
        cache_keys.append(f"yt_meta:{cache_key}")

    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                UPDATE youtube_cache SET
                    title = COALESCE($1, title),
                    channel_name = COALESCE($2, channel_name),
                    yt_video_id = COALESCE($3, yt_video_id),
                    uploaded_at = COALESCE(NULLIF(TRIM($4), ''), uploaded_at)
                WHERE video_id = $5
                """,
                records,
            )

    from services.cache_service import cache_delete_many

    await cache_delete_many(cache_keys)
    if invalidate_summary and has_summary_change:
        await _invalidate_archive_summary_cache()


async def get_cache_rows_needing_metadata(
    limit: int = 50,
    exclude_video_ids: list[str] | None = None,
    before_id: int | None = None,
):
    pool = await get_db()
    if before_id is not None:
        return await pool.fetch(
            f"""
            SELECT id, video_id, yt_video_id, title, channel_name, uploaded_at
            FROM youtube_cache
            WHERE ({_NEEDS_METADATA_SQL} OR ({_CACHE_NEEDS_UPLOAD_DATE_SQL}))
              AND id < $2
            ORDER BY id DESC
            LIMIT $1
            """,
            limit,
            before_id,
        )
    if exclude_video_ids:
        return await pool.fetch(
            f"""
            SELECT id, video_id, yt_video_id, title, channel_name, uploaded_at
            FROM youtube_cache
            WHERE ({_NEEDS_METADATA_SQL} OR ({_CACHE_NEEDS_UPLOAD_DATE_SQL}))
              AND NOT (video_id = ANY($2::text[]))
            ORDER BY id DESC
            LIMIT $1
            """,
            limit,
            exclude_video_ids,
        )
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, channel_name, uploaded_at
        FROM youtube_cache
        WHERE {_NEEDS_METADATA_SQL} OR ({_CACHE_NEEDS_UPLOAD_DATE_SQL})
        ORDER BY id DESC
        LIMIT $1
        """,
        limit,
    )


async def _run_yt_metadata_backfill_loop(
    fetch_batch_fn,
    row_to_update_fn,
    *,
    batch_size: int,
    max_total: int | None,
    delay_sec: float,
    invalidate_on_summary: bool = False,
) -> dict:
    from services.youtube import get_video_info_cached

    fixed = 0
    failed = 0
    processed = 0
    before_id: int | None = None
    attempted_ids: set[str] | None = None
    sem = asyncio.Semaphore(3)
    any_summary_updated = False

    async def _process_row(row):
        cache_key = row["video_id"]
        yt_id = (row["yt_video_id"] or "").strip() or extract_yt_id_from_cache_key(
            cache_key
        )
        if not yt_id:
            return None

        url = f"https://www.youtube.com/watch?v={yt_id}"
        async with sem:
            try:
                info = await get_video_info_cached(url)
            except Exception:
                info = None
        if delay_sec > 0:
            await asyncio.sleep(delay_sec)

        return row_to_update_fn(cache_key, yt_id, info)

    while True:
        if attempted_ids is None:
            try:
                rows = await fetch_batch_fn(batch_size, before_id=before_id)
            except TypeError:
                attempted_ids = set()
                rows = await fetch_batch_fn(
                    batch_size, exclude_video_ids=attempted_ids
                )
        else:
            rows = await fetch_batch_fn(
                batch_size, exclude_video_ids=attempted_ids
            )
        if not rows:
            break

        if max_total is not None:
            remaining = max_total - processed
            if remaining <= 0:
                break
            rows = rows[:remaining]

        if attempted_ids is not None:
            for r in rows:
                attempted_ids.add(r["video_id"])
        else:
            try:
                before_id = rows[-1]["id"]
            except (KeyError, IndexError, TypeError):
                before_id = None

        processed += len(rows)
        results = await asyncio.gather(*(_process_row(r) for r in rows), return_exceptions=True)
        batch_updates = []
        for res in results:
            if isinstance(res, tuple):
                batch_updates.append(res)
                if res[1] or res[2]:
                    any_summary_updated = True
                fixed += 1
            else:
                failed += 1

        if batch_updates:
            await _batch_update_cache_metadata(batch_updates, invalidate_summary=False)

        if (max_total is not None and processed >= max_total) or len(rows) < batch_size:
            break

    if invalidate_on_summary and any_summary_updated:
        await _invalidate_archive_summary_cache()

    return {"fixed": fixed, "failed": failed, "processed": processed}


async def backfill_youtube_cache_metadata(
    batch_size: int = 30,
    max_total: int | None = 500,
    delay_sec: float = 0.4,
) -> dict:
    """Fetch title/channel from YouTube for old cache rows missing metadata."""
    from services.youtube import uploaded_at_from_video_info

    def _to_update(cache_key: str, yt_id: str, info):
        uploaded = uploaded_at_from_video_info(info) if info else None
        has_title = bool(info and info.get("title"))
        if has_title or uploaded:
            return (
                cache_key,
                info.get("title") if has_title else None,
                info.get("uploader") if has_title else None,
                yt_id,
                uploaded,
            )
        return None

    return await _run_yt_metadata_backfill_loop(
        get_cache_rows_needing_metadata,
        _to_update,
        batch_size=batch_size,
        max_total=max_total,
        delay_sec=delay_sec,
        invalidate_on_summary=True,
    )


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


async def get_cache_rows_missing_upload_date(
    limit: int = 50,
    before_id: int | None = None,
):
    pool = await get_db()
    if before_id is not None:
        return await pool.fetch(
            """
            SELECT id, video_id, yt_video_id
            FROM youtube_cache
            WHERE (uploaded_at IS NULL OR TRIM(uploaded_at) = '')
              AND yt_video_id IS NOT NULL AND TRIM(yt_video_id) != ''
              AND id < $2
            ORDER BY id DESC
            LIMIT $1
            """,
            limit,
            before_id,
        )
    return await pool.fetch(
        """
        SELECT id, video_id, yt_video_id
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
    from services.youtube import get_video_info_cached, uploaded_at_from_video_info

    sem = asyncio.Semaphore(3)

    async def _fill_one(row):
        try:
            existing = row["uploaded_at"]
        except (KeyError, IndexError, TypeError):
            existing = None
        if existing and str(existing).strip():
            return None

        cache_key = row["video_id"]
        try:
            yt_id = (row["yt_video_id"] or "").strip() or extract_yt_id_from_cache_key(
                cache_key
            )
        except (KeyError, IndexError, TypeError):
            yt_id = extract_yt_id_from_cache_key(cache_key)

        if not yt_id:
            return None

        url = f"https://www.youtube.com/watch?v={yt_id}"
        async with sem:
            try:
                info = await get_video_info_cached(url)
            except Exception:
                info = None
        if delay_sec > 0:
            await asyncio.sleep(delay_sec)

        uploaded = uploaded_at_from_video_info(info) if info else None
        if not uploaded:
            return None

        return (cache_key, None, None, yt_id, uploaded)

    results = await asyncio.gather(*(_fill_one(r) for r in rows), return_exceptions=True)
    updates = [r for r in results if isinstance(r, tuple)]
    if updates:
        await _batch_update_cache_metadata(updates, invalidate_summary=False)
    return len(updates)


async def backfill_cache_upload_dates(
    batch_size: int = 40,
    max_total: int | None = 2000,
    delay_sec: float = 0.35,
) -> dict:
    from services.youtube import uploaded_at_from_video_info

    def _to_update(cache_key: str, yt_id: str, info):
        uploaded = uploaded_at_from_video_info(info) if info else None
        if uploaded:
            return (cache_key, None, None, yt_id, uploaded)
        return None

    return await _run_yt_metadata_backfill_loop(
        get_cache_rows_missing_upload_date,
        _to_update,
        batch_size=batch_size,
        max_total=max_total,
        delay_sec=delay_sec,
        invalidate_on_summary=False,
    )


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


_inflight_channels_load: asyncio.Task | None = None


async def _load_all_global_channels() -> list[dict]:
    global _inflight_channels_load
    from services.cache_service import cache_get, cache_set_many

    cached = await cache_get("yt_archive:channels_all")
    if isinstance(cached, list):
        return cached

    if _inflight_channels_load is not None and not _inflight_channels_load.done():
        return await asyncio.shield(_inflight_channels_load)

    async def _query() -> list[dict]:
        start_gen = _archive_channels_gen
        pool = await get_db()
        rows = await pool.fetch(
            f"""
            SELECT channel_name, COUNT(DISTINCT {_YT_GROUP_KEY_SQL}) AS video_count
            FROM youtube_cache
            WHERE {_CHANNEL_KNOWN_SQL}
              AND {_CACHE_HAS_FILES_SQL}
            GROUP BY channel_name
            ORDER BY video_count DESC, channel_name ASC
            """
        )
        serialized = [
            {"channel_name": r["channel_name"], "video_count": int(r["video_count"])}
            for r in rows
        ]
        if _archive_channels_gen == start_gen:
            await cache_set_many(
                {
                    "yt_archive:channels_all": serialized,
                    "yt_archive:count_channels": len(serialized),
                },
                ttl_sec=120,
            )
        return serialized

    task = asyncio.create_task(_query())
    _inflight_channels_load = task

    def _cleanup(done_task: asyncio.Task) -> None:
        global _inflight_channels_load
        if _inflight_channels_load is done_task:
            _inflight_channels_load = None
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)


async def get_global_channels_page(offset: int = 0, limit: int = CHANNELS_PAGE_SIZE):
    all_channels = await _load_all_global_channels()
    start = max(0, int(offset))
    end = start + max(0, int(limit))
    return all_channels[start:end]


async def count_global_channels() -> int:
    from services.cache_service import cache_get, cache_set

    cached = await cache_get("yt_archive:count_channels")
    if isinstance(cached, int):
        return cached

    cached_all = await cache_get("yt_archive:channels_all")
    if isinstance(cached_all, list):
        count = len(cached_all)
        await cache_set("yt_archive:count_channels", count, ttl_sec=120)
        return count

    pool = await get_db()
    val = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT channel_name)
        FROM youtube_cache
        WHERE channel_name IS NOT NULL AND TRIM(channel_name) != ''
          AND file_ids IS NOT NULL AND file_ids != '[]'
        """
    )
    count = int(val or 0)
    await cache_set("yt_archive:count_channels", count, ttl_sec=120)
    return count


async def _get_archive_version() -> str:
    from services.cache_service import cache_get

    ver = await cache_get("yt_archive:channels_ver")
    return str(ver) if ver is not None else "0"


def _channel_cache_hash(channel_name: str) -> str:
    import hashlib

    return hashlib.md5(channel_name.encode("utf-8")).hexdigest()[:16]


async def get_global_channel_videos_page(
    channel_name: str, offset: int = 0, limit: int = VIDEOS_PAGE_SIZE
):
    """One row per YouTube video (newest cache row per yt_video_id), version-cached."""
    from services.cache_service import cache_get, cache_set

    ver = await _get_archive_version()
    ch_hash = _channel_cache_hash(channel_name)
    cache_key = f"yt_archive:ch_vids:{ver}:{ch_hash}:{int(offset)}:{int(limit)}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list):
        return cached

    pool = await get_db()
    rows = await pool.fetch(
        f"""
        WITH latest AS (
            SELECT MAX(id) AS latest_id
            FROM youtube_cache
            WHERE channel_name = $1
              AND {_CACHE_HAS_FILES_SQL}
            GROUP BY {_YT_GROUP_KEY_SQL}
        )
        SELECT c.id, c.video_id, c.yt_video_id, c.title,
               c.format_type, c.quality, c.cached_at, c.uploaded_at, c.channel_name
        FROM youtube_cache c
        JOIN latest l ON c.id = l.latest_id
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT $2 OFFSET $3
        """,
        channel_name,
        limit,
        offset,
    )
    serialized = [dict(r) for r in rows]
    await cache_set(cache_key, serialized, ttl_sec=120)
    return serialized


async def count_global_channel_videos(channel_name: str) -> int:
    from services.cache_service import cache_get, cache_set

    ver = await _get_archive_version()
    ch_hash = _channel_cache_hash(channel_name)
    cache_key = f"yt_archive:ch_cnt:{ver}:{ch_hash}"
    cached = await cache_get(cache_key)
    if isinstance(cached, int):
        return cached

    pool = await get_db()
    val = await pool.fetchval(
        f"""
        SELECT COUNT(DISTINCT {_YT_GROUP_KEY_SQL})
        FROM youtube_cache
        WHERE channel_name = $1
          AND {_CACHE_HAS_FILES_SQL}
        """,
        channel_name,
    )
    count = int(val or 0)
    await cache_set(cache_key, count, ttl_sec=120)
    return count


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


def _escape_ilike(text: str) -> str:
    return (
        text.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


async def search_global_cache_by_title(query: str, limit: int = 15):
    pool = await get_db()
    pattern = f"%{_escape_ilike(query)}%"
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, channel_name,
               format_type, cached_at, uploaded_at
        FROM youtube_cache
        WHERE title ILIKE $1 ESCAPE '\\'
          AND {_CACHE_HAS_FILES_SQL}
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT $2
        """,
        pattern,
        limit,
    )


async def search_global_cache_by_channel(query: str, limit: int = 15):
    pool = await get_db()
    pattern = f"%{_escape_ilike(query)}%"
    return await pool.fetch(
        f"""
        SELECT id, video_id, yt_video_id, title, channel_name,
               format_type, cached_at, uploaded_at
        FROM youtube_cache
        WHERE channel_name ILIKE $1 ESCAPE '\\'
          AND {_CACHE_HAS_FILES_SQL}
        ORDER BY {_CHANNEL_VIDEOS_ORDER_SQL}
        LIMIT $2
        """,
        pattern,
        limit,
    )


_YT_VIEWS_PENDING_HASH = "bale:yt:views_pending"
_YT_VIEWS_FLUSH_THRESHOLD = 25
_YT_VIEWS_RETRY_COOLDOWN_SEC = 15.0
_yt_views_retry_after = 0.0
_views_flush_lock = asyncio.Lock()
_POP_ALL_HASH_LUA = """
local vals = redis.call("HGETALL", KEYS[1])
if #vals > 0 then
    redis.call("DEL", KEYS[1])
end
return vals
"""


async def flush_pending_yt_views() -> int:
    """Flush Redis-buffered YouTube view increments to PostgreSQL in one batch."""
    from services.redis_client import get_async_redis

    redis = get_async_redis()
    if redis is None:
        return 0

    async with _views_flush_lock:
        try:
            raw = await redis.eval(_POP_ALL_HASH_LUA, 1, _YT_VIEWS_PENDING_HASH)
        except Exception:
            return 0
        if not raw:
            return 0

        video_ids: list[str] = []
        deltas: list[int] = []
        for i in range(0, len(raw) - 1, 2):
            vid = raw[i]
            try:
                delta = int(raw[i + 1])
            except (TypeError, ValueError):
                continue
            if vid and delta > 0:
                video_ids.append(vid)
                deltas.append(delta)

        if not video_ids:
            return 0

        try:
            pool = await get_db()
            await pool.execute(
                """
                UPDATE youtube_cache AS yc
                SET view_count = COALESCE(yc.view_count, 0) + v.delta
                FROM (
                    SELECT UNNEST($1::text[]) AS video_id, UNNEST($2::int[]) AS delta
                ) AS v
                WHERE yc.video_id = v.video_id
                """,
                video_ids,
                deltas,
            )
            global _yt_views_retry_after
            _yt_views_retry_after = 0.0
            return len(video_ids)
        except BaseException as exc:
            if isinstance(exc, Exception):
                _yt_views_retry_after = time.monotonic() + _YT_VIEWS_RETRY_COOLDOWN_SEC
            # Restore deltas to Redis on transient DB error or cancellation
            try:
                pipe = redis.pipeline()
                for vid, delta in zip(video_ids, deltas):
                    pipe.hincrby(_YT_VIEWS_PENDING_HASH, vid, delta)
                await pipe.execute()
            except Exception:
                pass
            raise


async def increment_yt_video_view(video_id: str):
    from services.redis_client import get_async_redis

    redis = get_async_redis()
    if redis is not None:
        try:
            pipe = redis.pipeline()
            pipe.hincrby(_YT_VIEWS_PENDING_HASH, video_id, 1)
            pipe.hlen(_YT_VIEWS_PENDING_HASH)
            res = await pipe.execute()
            pending_len = int(res[1] or 0)
            if (
                pending_len >= _YT_VIEWS_FLUSH_THRESHOLD
                and time.monotonic() >= _yt_views_retry_after
            ):
                try:
                    await flush_pending_yt_views()
                except Exception:
                    pass
            return
        except Exception:
            pass

    pool = await get_db()
    await pool.execute(
        "UPDATE youtube_cache SET view_count = view_count + 1 WHERE video_id = $1",
        video_id,
    )


async def get_top_cached_videos(limit: int = 10):
    from services.cache_service import cache_get, cache_set

    cache_key = f"yt_archive:top:{limit}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list):
        return cached

    await flush_pending_yt_views()
    pool = await get_db()
    rows = await pool.fetch(
        f"""
        SELECT video_id, file_ids, view_count, format_type
        FROM youtube_cache
        WHERE {_CACHE_HAS_FILES_SQL}
        ORDER BY view_count DESC
        LIMIT $1
        """,
        limit,
    )
    serialized = [
        {
            "video_id": r["video_id"],
            "file_ids": r["file_ids"],
            "view_count": int(r["view_count"] or 0),
            "format_type": (
                (r["format_type"] if "format_type" in r else "video_zip")
                or "video_zip"
            ),
        }
        for r in rows
    ]
    await cache_set(cache_key, serialized, ttl_sec=120)
    return serialized
