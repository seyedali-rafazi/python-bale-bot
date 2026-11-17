# core/database/github.py

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today


async def get_gh_downloads(user_id) -> int:
    return await get_period_usage(
        user_id,
        "gh_count",
        "gh_date",
        get_tehran_today(),
        cache_service="github",
    )


async def increment_gh_downloads(user_id) -> int:
    return await increment_period_usage(
        user_id,
        "gh_count",
        "gh_date",
        get_tehran_today(),
        monitor_section="github",
        cache_service="github",
    )
