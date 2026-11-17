# core/database/telegram.py

from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today


async def get_tg_downloads(user_id: str) -> int:
    return await get_period_usage(
        user_id,
        "tg_count",
        "tg_date",
        get_tehran_today(),
        cache_service="telegram",
    )


async def increment_tg_downloads(user_id: str) -> None:
    await increment_period_usage(
        user_id,
        "tg_count",
        "tg_date",
        get_tehran_today(),
        monitor_section="telegram",
        cache_service="telegram",
    )
