# core/database/monitoring.py
"""Event logging and aggregation for hourly bot monitoring reports."""

from __future__ import annotations

from datetime import datetime, timedelta

from .connection import get_db
from .utils import TEHRAN_TZ, get_tehran_now_full, get_tehran_today

SECTION_LABELS = {
    "youtube": "🎬 یوتیوب",
    "music": "🎵 موسیقی",
    "pinterest": "📌 پینترست",
    "tiktok": "🎭 تیک‌تاک",
    "github": "💻 گیت‌هاب",
    "instagram": "📸 اینستاگرام",
    "web_search": "🔍 جستجوی وب",
    "yt_archive": "📚 آرشیو یوتیوب",
    "ai_chat": "🤖 هوش مصنوعی",
    "cloud": "☁️ فضای ابری",
    "translation": "🌐 ترجمه",
    "weather": "🌤 هواشناسی",
    "payment": "💳 پرداخت",
    "telegram": "✈️ تلگرام",
    "image_processing": "🖼 پردازش تصویر",
}

ALL_SECTIONS = list(SECTION_LABELS.keys())

_TODAY_ACTIVITY_SQL = """
    yt_date = ? OR music_date = ? OR pinterest_date = ?
    OR tt_dl_date = ? OR ig_dl_date = ? OR ig_exp_date = ?
    OR gh_date = ? OR web_search_dl_date = ? OR arc_fetch_date = ?
    OR ai_chat_date = ? OR tg_date = ?
"""


async def log_monitor_event(
    section: str,
    user_id: str | None = None,
    event_type: str = "upload_success",
) -> None:
    conn = await get_db()
    await conn.execute(
        """
        INSERT INTO monitoring_events (section, event_type, user_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (section, event_type, user_id, get_tehran_now_full()),
    )
    await conn.commit()


async def log_upload_success(section: str, user_id: str | None = None) -> None:
    await log_monitor_event(section, user_id, "upload_success")


async def log_user_active(user_id: str) -> None:
    await log_monitor_event("bot", user_id, "user_active")


async def _section_counts_between(start: str, end: str) -> dict[str, int]:
    conn = await get_db()
    counts = {section: 0 for section in ALL_SECTIONS}
    async with conn.execute(
        """
        SELECT section, COUNT(*) AS cnt
        FROM monitoring_events
        WHERE event_type = 'upload_success'
          AND created_at >= ?
          AND created_at < ?
        GROUP BY section
        """,
        (start, end),
    ) as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        section = row[0] if not isinstance(row, dict) else row["section"]
        cnt = row[1] if not isinstance(row, dict) else row["cnt"]
        if section in counts:
            counts[section] = cnt
    return counts


async def _count_responses_between(start: str, end: str) -> int:
    conn = await get_db()
    async with conn.execute(
        """
        SELECT COUNT(*) FROM monitoring_events
        WHERE event_type = 'upload_success'
          AND created_at >= ?
          AND created_at < ?
        """,
        (start, end),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def _count_active_users_between(start: str, end: str) -> int:
    conn = await get_db()
    async with conn.execute(
        """
        SELECT COUNT(DISTINCT user_id) FROM monitoring_events
        WHERE user_id IS NOT NULL
          AND created_at >= ?
          AND created_at < ?
        """,
        (start, end),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def count_active_users_today() -> int:
    today = get_tehran_today()
    today_start = f"{today} 00:00:00"
    conn = await get_db()
    params = (today,) * 11 + (today_start,)
    async with conn.execute(
        f"""
        SELECT COUNT(DISTINCT user_id) FROM (
            SELECT user_id FROM users
            WHERE user_id IS NOT NULL AND ({_TODAY_ACTIVITY_SQL})
            UNION
            SELECT user_id FROM monitoring_events
            WHERE user_id IS NOT NULL AND created_at >= ?
        )
        """,
        params,
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


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

    hour_counts = await _section_counts_between(hour_start, hour_end)
    today_counts = await _section_counts_between(today_start, tomorrow)

    return {
        "report_date": today,
        "hour_label": f"{label_start} – {label_end}",
        "hour_start": hour_start,
        "hour_end": hour_end,
        "hour_section_counts": hour_counts,
        "today_section_counts": today_counts,
        "hour_responses": await _count_responses_between(hour_start, hour_end),
        "today_responses": await _count_responses_between(today_start, tomorrow),
        "hour_active_users": await _count_active_users_between(hour_start, hour_end),
        "today_active_users": await count_active_users_today(),
    }


async def purge_old_monitoring_events(days: int = 14) -> int:
    cutoff = (datetime.now(TEHRAN_TZ) - timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = await get_db()
    async with conn.execute(
        "SELECT COUNT(*) FROM monitoring_events WHERE created_at < ?",
        (cutoff,),
    ) as cursor:
        row = await cursor.fetchone()
        to_delete = row[0] if row else 0
    if to_delete:
        await conn.execute(
            "DELETE FROM monitoring_events WHERE created_at < ?",
            (cutoff,),
        )
        await conn.commit()
    return to_delete
