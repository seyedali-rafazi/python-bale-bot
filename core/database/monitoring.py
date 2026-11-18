# core/database/monitoring.py
"""Event logging and aggregation for hourly bot monitoring reports."""

from __future__ import annotations

from datetime import datetime, timedelta

from .connection import get_db
from .utils import TEHRAN_TZ, get_tehran_now_full, get_tehran_today

SECTION_LABELS = {
    "youtube":          "🎬 یوتیوب",
    "music":            "🎵 موسیقی",
    "pinterest":        "📌 پینترست",
    "tiktok":           "🎭 تیک‌تاک",
    "github":           "💻 گیت‌هاب",
    "instagram":        "📸 اینستاگرام",
    "web_search":       "🔍 جستجوی وب",
    "yt_archive":       "📚 آرشیو یوتیوب",
    "ai_chat":          "🤖 هوش مصنوعی",
    "cloud":            "☁️ فضای ابری",
    "translation":      "🌐 ترجمه",
    "weather":          "🌤 هواشناسی",
    "payment":          "💳 پرداخت",
    "telegram":         "✈️ تلگرام",
    "image_processing": "🖼 پردازش تصویر",
    "kaggle":           "🗂 کاگل",
    "book":             "📖 کتاب",
    "software":         "📦 نرم‌افزار",
}

ALL_SECTIONS = list(SECTION_LABELS.keys())

_TODAY_ACTIVITY_SQL = """
    yt_date = $1 OR music_date = $1 OR pinterest_date = $1
    OR tt_dl_date = $1 OR ig_dl_date = $1 OR ig_exp_date = $1
    OR gh_date = $1 OR web_search_dl_date = $1 OR arc_fetch_date = $1
    OR ai_chat_date = $1 OR tg_date = $1
"""


async def log_monitor_event(
    section: str,
    user_id: str | None = None,
    event_type: str = "upload_success",
) -> None:
    pool = await get_db()
    uid = str(user_id) if user_id is not None else None
    await pool.execute(
        """
        INSERT INTO monitoring_events (section, event_type, user_id, created_at)
        VALUES ($1, $2, $3, $4)
        """,
        section,
        event_type,
        uid,
        get_tehran_now_full(),
    )


async def log_upload_success(section: str, user_id: str | None = None) -> None:
    await log_monitor_event(section, user_id, "upload_success")


async def log_upload_failed(section: str, user_id: str | None = None) -> None:
    """Log a failed request/upload for a given section."""
    await log_monitor_event(section, user_id, "upload_failed")


async def log_user_active(user_id: str) -> None:
    await log_monitor_event("bot", user_id, "user_active")


async def _section_counts_between(
    start: str, end: str, event_type: str = "upload_success"
) -> dict[str, int]:
    pool = await get_db()
    counts = {section: 0 for section in ALL_SECTIONS}
    rows = await pool.fetch(
        """
        SELECT section, COUNT(*) AS cnt
        FROM monitoring_events
        WHERE event_type = $1
          AND created_at >= $2
          AND created_at < $3
        GROUP BY section
        """,
        event_type,
        start,
        end,
    )
    for row in rows:
        section = row["section"]
        if section in counts:
            counts[section] = int(row["cnt"])
    return counts


async def _count_responses_between(
    start: str, end: str, event_type: str = "upload_success"
) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        """
        SELECT COUNT(*) FROM monitoring_events
        WHERE event_type = $1
          AND created_at >= $2
          AND created_at < $3
        """,
        event_type,
        start,
        end,
    )
    return int(val or 0)


async def _count_active_users_between(start: str, end: str) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT user_id) FROM monitoring_events
        WHERE user_id IS NOT NULL
          AND created_at >= $1
          AND created_at < $2
        """,
        start,
        end,
    )
    return int(val or 0)


async def count_active_users_today() -> int:
    today = get_tehran_today()
    today_start = f"{today} 00:00:00"
    pool = await get_db()
    val = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT user_id) AS active_users
        FROM monitoring_events
        WHERE user_id IS NOT NULL
          AND created_at >= $1
        """,
        today_start,
    )
    return int(val or 0)


def _last_completed_hour_range() -> tuple[str, str, str, str]:
    """Return (hour_start, hour_end, label_start, label_end) for the previous full hour."""
    now = datetime.now(TEHRAN_TZ)
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    hour_start = hour_end - timedelta(hours=1)
    return (
        hour_start.strftime("%Y-%m-%d %H:%M:%S"),
        hour_end.strftime("%Y-%m-%d %H:%M:%S"),
        hour_start.strftime("%H:%M"),
        hour_end.strftime("%H:%M"),
    )


async def get_monitoring_report_data() -> dict:
    hour_start, hour_end, label_start, label_end = _last_completed_hour_range()
    today = get_tehran_today()
    today_start = f"{today} 00:00:00"
    tomorrow = (
        datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=TEHRAN_TZ)
        + timedelta(days=1)
    ).strftime("%Y-%m-%d 00:00:00")

    window_start = min(hour_start, today_start)
    window_end = max(hour_end, tomorrow)

    pool = await get_db()
    rows = await pool.fetch(
        """
        SELECT
            section,
            event_type,
            COUNT(*) FILTER (WHERE created_at >= $3 AND created_at < $4) AS hour_cnt,
            COUNT(*) FILTER (WHERE created_at >= $5 AND created_at < $6) AS today_cnt
        FROM monitoring_events
        WHERE created_at >= $1
          AND created_at < $2
          AND event_type IN ('upload_success', 'upload_failed')
        GROUP BY section, event_type
        """,
        window_start,
        window_end,
        hour_start,
        hour_end,
        today_start,
        tomorrow,
    )

    hour_ok = {section: 0 for section in ALL_SECTIONS}
    today_ok = {section: 0 for section in ALL_SECTIONS}
    hour_fail = {section: 0 for section in ALL_SECTIONS}
    today_fail = {section: 0 for section in ALL_SECTIONS}
    hour_responses = 0
    today_responses = 0
    hour_failures = 0
    today_failures = 0

    for row in rows:
        section = row["section"]
        ev_type = row["event_type"]
        h_cnt = int(row["hour_cnt"] or 0)
        t_cnt = int(row["today_cnt"] or 0)

        if ev_type == "upload_success":
            hour_responses += h_cnt
            today_responses += t_cnt
            if section in hour_ok:
                hour_ok[section] = h_cnt
                today_ok[section] = t_cnt
        elif ev_type == "upload_failed":
            hour_failures += h_cnt
            today_failures += t_cnt
            if section in hour_fail:
                hour_fail[section] = h_cnt
                today_fail[section] = t_cnt

    return {
        "report_date": today,
        "hour_label": f"{label_start} – {label_end}",
        "hour_start": hour_start,
        "hour_end": hour_end,
        "hour_section_counts": hour_ok,
        "today_section_counts": today_ok,
        "hour_responses": hour_responses,
        "today_responses": today_responses,
        "hour_section_fails": hour_fail,
        "today_section_fails": today_fail,
        "hour_failures": hour_failures,
        "today_failures": today_failures,
        "hour_active_users": await _count_active_users_between(hour_start, hour_end),
        "today_active_users": await count_active_users_today(),
    }


async def purge_old_monitoring_events(days: int = 14) -> int:
    cutoff = (datetime.now(TEHRAN_TZ) - timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    pool = await get_db()
    deleted = await pool.fetchval(
        """
        WITH deleted AS (
            DELETE FROM monitoring_events
            WHERE created_at < $1
            RETURNING 1
        )
        SELECT COUNT(*) FROM deleted
        """,
        cutoff,
    )
    return int(deleted or 0)
