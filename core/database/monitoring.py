# core/database/monitoring.py
"""Event logging and aggregation for hourly bot monitoring reports."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta

from .connection import get_db
from .utils import TEHRAN_TZ, get_tehran_now_full, get_tehran_today

_PENDING_MONITOR_FLUSH_THRESHOLD = 25
_pending_monitor_events: list[tuple[str, str, str | None, str]] = []
_monitor_flush_lock = asyncio.Lock()
_active_user_hour_seen: OrderedDict[str, str] = OrderedDict()
_ACTIVE_USER_SEEN_CAP = 20000

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


async def flush_pending_monitoring_events() -> int:
    """Flush buffered monitoring events to PostgreSQL in a single UNNEST INSERT."""
    if not _pending_monitor_events:
        return 0
    async with _monitor_flush_lock:
        if not _pending_monitor_events:
            return 0
        batch = _pending_monitor_events.copy()
        _pending_monitor_events.clear()

        sections = [e[0] for e in batch]
        event_types = [e[1] for e in batch]
        user_ids = [e[2] for e in batch]
        created_ats = [e[3] for e in batch]

        try:
            pool = await get_db()
            await pool.execute(
                """
                INSERT INTO monitoring_events (section, event_type, user_id, created_at)
                SELECT UNNEST($1::text[]), UNNEST($2::text[]), UNNEST($3::text[]), UNNEST($4::text[])
                """,
                sections,
                event_types,
                user_ids,
                created_ats,
            )
            return len(batch)
        except Exception:
            # Restore batch on transient DB error
            _pending_monitor_events[:0] = batch
            raise


async def log_monitor_event(
    section: str,
    user_id: str | None = None,
    event_type: str = "upload_success",
) -> None:
    uid = str(user_id) if user_id is not None else None
    _pending_monitor_events.append(
        (section, event_type, uid, get_tehran_now_full())
    )
    if len(_pending_monitor_events) >= _PENDING_MONITOR_FLUSH_THRESHOLD:
        await flush_pending_monitoring_events()


async def log_upload_success(section: str, user_id: str | None = None) -> None:
    await log_monitor_event(section, user_id, "upload_success")


async def log_upload_failed(section: str, user_id: str | None = None) -> None:
    """Log a failed request/upload for a given section."""
    await log_monitor_event(section, user_id, "upload_failed")


async def log_user_active(user_id: str) -> None:
    uid = str(user_id)
    hour_key = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H")
    if _active_user_hour_seen.get(uid) == hour_key:
        _active_user_hour_seen.move_to_end(uid)
        return
    _active_user_hour_seen[uid] = hour_key
    _active_user_hour_seen.move_to_end(uid)
    while len(_active_user_hour_seen) > _ACTIVE_USER_SEEN_CAP:
        _active_user_hour_seen.popitem(last=False)
    await log_monitor_event("bot", uid, "user_active")


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
    await flush_pending_monitoring_events()
    today = get_tehran_today()
    today_start = f"{today} 00:00:00"
    tomorrow = (
        datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=TEHRAN_TZ)
        + timedelta(days=1)
    ).strftime("%Y-%m-%d 00:00:00")
    pool = await get_db()
    val = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT user_id) AS active_users
        FROM monitoring_events
        WHERE user_id IS NOT NULL
          AND created_at >= $1
          AND created_at < $2
        """,
        today_start,
        tomorrow,
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
    await flush_pending_monitoring_events()
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
        WITH window_events AS (
            SELECT section, event_type, user_id, created_at
            FROM monitoring_events
            WHERE created_at >= $1
              AND created_at < $2
        )
        SELECT
            section,
            event_type,
            COUNT(*) FILTER (WHERE created_at >= $3 AND created_at < $4) AS hour_cnt,
            COUNT(*) FILTER (WHERE created_at >= $5 AND created_at < $6) AS today_cnt,
            NULL::bigint AS hour_active_users,
            NULL::bigint AS today_active_users
        FROM window_events
        WHERE event_type IN ('upload_success', 'upload_failed')
        GROUP BY section, event_type
        UNION ALL
        SELECT
            '__active__' AS section,
            '__active__' AS event_type,
            0 AS hour_cnt,
            0 AS today_cnt,
            COUNT(DISTINCT user_id) FILTER (
                WHERE user_id IS NOT NULL AND created_at >= $3 AND created_at < $4
            ) AS hour_active_users,
            COUNT(DISTINCT user_id) FILTER (
                WHERE user_id IS NOT NULL AND created_at >= $5 AND created_at < $6
            ) AS today_active_users
        FROM window_events
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
    hour_active_users = 0
    today_active_users = 0

    for row in rows:
        section = row["section"]
        ev_type = row["event_type"]
        if section == "__active__" and ev_type == "__active__":
            hour_active_users = int(row["hour_active_users"] or 0)
            today_active_users = int(row["today_active_users"] or 0)
            continue

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
        "hour_active_users": hour_active_users,
        "today_active_users": today_active_users,
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
