# core/database/user_yt_archive.py
# Per-user daily limits for fetching from the shared global YouTube cache.

from .connection import get_db
from .utils import get_tehran_today
from .vip import is_vip
from .youtube import (
    count_global_cache,
    count_global_channels,
    get_global_channels_page,
    get_global_channel_videos_page,
    count_global_channel_videos,
    get_cache_entry_by_rowid,
    search_global_cache_by_title,
    search_global_cache_by_channel,
    CHANNELS_PAGE_SIZE,
    VIDEOS_PAGE_SIZE,
)

ARCHIVE_LIMIT_FREE = 2
ARCHIVE_LIMIT_VIP = 20


async def get_user_archive_limit(user_id: str) -> int:
    vip = await is_vip(user_id)
    return ARCHIVE_LIMIT_VIP if vip == 1 else ARCHIVE_LIMIT_FREE


async def get_archive_fetches_today(user_id: str) -> int:
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT arc_fetch_count, arc_fetch_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["arc_fetch_date"] == today:
            return row["arc_fetch_count"] or 0
        return 0


async def can_user_fetch_from_archive(user_id: str) -> tuple[bool, int, int]:
    """Returns (allowed, used_today, limit)."""
    limit = await get_user_archive_limit(user_id)
    used = await get_archive_fetches_today(user_id)
    return used < limit, used, limit


async def increment_archive_fetch(user_id: str):
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT arc_fetch_count, arc_fetch_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        count = 1 if row["arc_fetch_date"] != today else (row["arc_fetch_count"] or 0) + 1
        await conn.execute(
            "UPDATE users SET arc_fetch_count = ?, arc_fetch_date = ? WHERE user_id = ?",
            (count, today, user_id),
        )
    await conn.commit()


# Re-export global cache queries for handlers
count_user_archive = count_global_cache
get_user_channels_page = get_global_channels_page
count_user_channels = count_global_channels
get_channel_videos_page = get_global_channel_videos_page
count_channel_videos = count_global_channel_videos
get_archive_entry = get_cache_entry_by_rowid
search_archive_by_title = search_global_cache_by_title
search_archive_by_channel = search_global_cache_by_channel
