# core/database/tiktok.py

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today


async def get_tt_downloads(user_id) -> int:
    return await get_period_usage(
        user_id,
        "tt_dl_count",
        "tt_dl_date",
        get_tehran_today(),
        cache_service="tiktok",
    )


async def increment_tt_downloads(user_id) -> int:
    return await increment_period_usage(
        user_id,
        "tt_dl_count",
        "tt_dl_date",
        get_tehran_today(),
        monitor_section="tiktok",
        cache_service="tiktok",
    )
