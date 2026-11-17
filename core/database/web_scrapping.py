# core/database/web_scrapping.py

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today


async def get_web_search_downloads(user_id) -> int:
    """Get web search downloads count for today."""
    return await get_period_usage(
        user_id,
        "web_search_dl_count",
        "web_search_dl_date",
        get_tehran_today(),
        cache_service="web_search",
    )


async def increment_web_search_downloads(user_id) -> int:
    """Increment web search downloads count and return new count."""
    return await increment_period_usage(
        user_id,
        "web_search_dl_count",
        "web_search_dl_date",
        get_tehran_today(),
        monitor_section="web_search",
        cache_service="web_search",
    )
