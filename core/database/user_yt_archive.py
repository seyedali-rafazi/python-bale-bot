# core/database/user_yt_archive.py
# Per-user limits for fetching from the shared global YouTube cache.
# Free: 2 per week (reset Saturday 00:00 Tehran). VIP: 20 per day.

from .connection import get_db
from .utils import get_tehran_today, get_tehran_archive_week_key
from .vip import is_vip
from .youtube import (
    count_global_cache,
    count_global_channels,
    get_global_channels_page,
    get_global_channel_videos_page,
    count_global_channel_videos,
    get_cache_entry_by_rowid,
    get_cache_variants_for_video,
    dedupe_archive_rows,
    search_global_cache_by_title,
    search_global_cache_by_channel,
    CHANNELS_PAGE_SIZE,
    VIDEOS_PAGE_SIZE,
)

ARCHIVE_LIMIT_FREE = 2
ARCHIVE_LIMIT_VIP = 20


def _archive_period_key(is_vip: int) -> str:
    if is_vip == 1:
        return get_tehran_today()
    return get_tehran_archive_week_key()


async def get_user_archive_limit(user_id: str) -> int:
    vip = await is_vip(user_id)
    return ARCHIVE_LIMIT_VIP if vip == 1 else ARCHIVE_LIMIT_FREE


async def get_archive_fetches_used(user_id: str) -> int:
    vip = await is_vip(user_id)
    period = _archive_period_key(vip)
    conn = await get_db()
    async with conn.execute(
        "SELECT arc_fetch_count, arc_fetch_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["arc_fetch_date"] == period:
            return row["arc_fetch_count"] or 0
        return 0


async def get_archive_fetches_today(user_id: str) -> int:
    """Backward-compatible alias."""
    return await get_archive_fetches_used(user_id)


async def can_user_fetch_from_archive(user_id: str) -> tuple[bool, int, int]:
    """Returns (allowed, used_in_period, limit)."""
    limit = await get_user_archive_limit(user_id)
    used = await get_archive_fetches_used(user_id)
    return used < limit, used, limit


async def increment_archive_fetch(user_id: str):
    vip = await is_vip(user_id)
    period = _archive_period_key(vip)
    conn = await get_db()
    async with conn.execute(
        "SELECT arc_fetch_count, arc_fetch_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        count = 1 if row["arc_fetch_date"] != period else (row["arc_fetch_count"] or 0) + 1
        await conn.execute(
            "UPDATE users SET arc_fetch_count = ?, arc_fetch_date = ? WHERE user_id = ?",
            (count, period, user_id),
        )
    await conn.commit()
    from .monitoring import log_upload_success

    await log_upload_success("yt_archive", user_id)


def archive_limit_period_label(is_vip: int) -> str:
    if is_vip == 1:
        return "روزانه (ریست نیمه‌شب تهران)"
    return "هفتگی (ریست شنبه نیمه‌شب تهران)"


# Re-export global cache queries for handlers
count_user_archive = count_global_cache
get_user_channels_page = get_global_channels_page
count_user_channels = count_global_channels
get_channel_videos_page = get_global_channel_videos_page
count_channel_videos = count_global_channel_videos
get_archive_entry = get_cache_entry_by_rowid
get_archive_variants = get_cache_variants_for_video
search_archive_by_title = search_global_cache_by_title
search_archive_by_channel = search_global_cache_by_channel
