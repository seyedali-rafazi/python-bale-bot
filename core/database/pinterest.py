# core/database/pinterest.py

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today


async def get_pinterest_downloads(user_id) -> int:
    return await get_period_usage(
        user_id,
        "pinterest_count",
        "pinterest_date",
        get_tehran_today(),
        cache_service="pinterest",
    )


async def increment_pinterest_downloads(user_id) -> int:
    return await increment_period_usage(
        user_id,
        "pinterest_count",
        "pinterest_date",
        get_tehran_today(),
        monitor_section="pinterest",
        cache_service="pinterest",
    )
