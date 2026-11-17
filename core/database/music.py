# core/database/music.py

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today


async def get_music_downloads(user_id) -> int:
    return await get_period_usage(
        user_id,
        "music_count",
        "music_date",
        get_tehran_today(),
        cache_service="music",
    )


async def increment_music_downloads(user_id) -> int:
    return await increment_period_usage(
        user_id,
        "music_count",
        "music_date",
        get_tehran_today(),
        monitor_section="music",
        cache_service="music",
    )
