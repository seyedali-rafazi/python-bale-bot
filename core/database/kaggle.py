# core/database/kaggle.py

from core.limits import FREE_LIMITS, VIP_LIMITS
from .counters import get_period_usage, increment_period_usage
from .utils import get_tehran_today

KAGGLE_LIMIT_FREE = FREE_LIMITS["kaggle_download"]
KAGGLE_LIMIT_VIP = VIP_LIMITS["kaggle_download"]


async def get_kaggle_downloads(user_id: str) -> int:
    """Returns the number of Kaggle downloads used today by user_id."""
    return await get_period_usage(
        user_id,
        "kaggle_count",
        "kaggle_date",
        get_tehran_today(),
        cache_service="kaggle",
    )


async def increment_kaggle_downloads(user_id: str) -> None:
    """Increments Kaggle download counter for today."""
    await increment_period_usage(
        user_id,
        "kaggle_count",
        "kaggle_date",
        get_tehran_today(),
        monitor_section="kaggle",
        cache_service="kaggle",
    )
