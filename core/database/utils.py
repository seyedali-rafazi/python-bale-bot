# core/database/utils.py

from datetime import datetime, timedelta
import pytz

TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def get_tehran_today():
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")


def get_tehran_now_full():
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_tehran_archive_week_key():
    """Start of current free-tier archive week (Saturday 00:00 Tehran)."""
    now = datetime.now(TEHRAN_TZ)
    days_back = (now.weekday() - 5) % 7
    week_start = (now - timedelta(days=days_back)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return week_start.strftime("%Y-%m-%d")
