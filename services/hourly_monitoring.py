# services/hourly_monitoring.py
"""Build and send hourly monitoring reports to a Bale channel."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from io import BytesIO

from telegram import InputFile
from telegram.ext import ContextTypes

from core.database import get_monitoring_report_data, get_total_users, get_total_vip_users
from core.database.monitoring import ALL_SECTIONS, SECTION_LABELS, purge_old_monitoring_events
from core.database.utils import TEHRAN_TZ

logger = logging.getLogger(__name__)

MONITOR_CHANNEL_ID = os.getenv("MONITOR_CHANNEL_ID", "@digimonitoring").strip()
MONITORING_ENABLED = os.getenv("MONITORING_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _format_section_block(
    ok_counts: dict[str, int],
    fail_counts: dict[str, int],
) -> list[str]:
    """
    Format one table-row per active section showing:
      Label  ✅ N  ❌ M
    Only sections that had at least one event (success or failure) are shown.
    """
    lines: list[str] = []
    total_ok = 0
    total_fail = 0

    for section in ALL_SECTIONS:
        ok = ok_counts.get(section, 0)
        fail = fail_counts.get(section, 0)
        if ok == 0 and fail == 0:
            continue
        total_ok += ok
        total_fail += fail
        label = SECTION_LABELS[section]
        lines.append(f"  {label}: ✅ {ok}  ❌ {fail}")

    if not lines:
        lines.append("  — فعالیتی ثبت نشده")
    else:
        lines.append(f"  {'─' * 20}")
        lines.append(f"  📦 جمع: ✅ {total_ok}  ❌ {total_fail}")

    return lines


def build_monitoring_report_text(data: dict, total_users: int, vip_users: int) -> str:
    now_label = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M")
    normal_users = total_users - vip_users

    hour_ok   = data["hour_section_counts"]
    hour_fail = data["hour_section_fails"]
    day_ok    = data["today_section_counts"]
    day_fail  = data["today_section_fails"]

    lines = [
        "📊 گزارش ساعتی ربات",
        f"🕐 زمان ارسال: {now_label} (تهران)",
        f"⏱ بازه گزارش: {data['hour_label']}",
        f"📅 تاریخ: {data['report_date']}",
        "",
        "👥 کاربران فعال",
        f"  • امروز: {data['today_active_users']} نفر",
        f"  • این ساعت: {data['hour_active_users']} نفر",
        "",
        "📊 عملکرد این ساعت  (✅ موفق  |  ❌ ناموفق)",
        *_format_section_block(hour_ok, hour_fail),
        "",
        f"💬 کل این ساعت: ✅ {data['hour_responses']}  ❌ {data['hour_failures']}",
        "",
        "📈 عملکرد امروز (از نیمه‌شب)  (✅ موفق  |  ❌ ناموفق)",
        *_format_section_block(day_ok, day_fail),
        "",
        f"💬 کل امروز: ✅ {data['today_responses']}  ❌ {data['today_failures']}",
        "",
        "📋 آمار کلی کاربران",
        f"  • کل کاربران: {total_users}",
        f"  • VIP: {vip_users}",
        f"  • عادی: {normal_users}",
    ]
    return "\n".join(lines)


def _report_filename(data: dict) -> str:
    stamp = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d_%H-%M")
    return f"monitor_report_{stamp}.txt"


async def send_monitoring_report_document(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    report_text: str,
    data: dict,
) -> None:
    """Send report as a .txt file so channel text echoes cannot re-trigger handlers."""
    filename = _report_filename(data)
    caption = f"📊 گزارش ساعتی ربات — {data['hour_label']} ({data['report_date']})"
    payload = BytesIO(report_text.encode("utf-8"))
    payload.name = filename

    await context.bot.send_document(
        chat_id=chat_id,
        document=InputFile(payload, filename=filename),
        caption=caption,
    )


async def send_hourly_monitoring_report(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    also_send_to: str | None = None,
) -> None:
    if not MONITORING_ENABLED:
        return

    try:
        data = await get_monitoring_report_data()
        total_users = await get_total_users()
        vip_users = await get_total_vip_users()
        report = build_monitoring_report_text(data, total_users, vip_users)

        targets: list[str] = []
        if MONITOR_CHANNEL_ID:
            targets.append(MONITOR_CHANNEL_ID)
        elif not also_send_to:
            logger.warning("MONITOR_CHANNEL_ID is not set; skipping hourly report")
            return

        if also_send_to and also_send_to not in targets:
            targets.append(also_send_to)

        for chat_id in targets:
            await send_monitoring_report_document(context, chat_id, report, data)
            logger.info(
                "Monitoring report document sent to %s (%s–%s)",
                chat_id,
                data["hour_start"],
                data["hour_end"],
            )

        deleted = await purge_old_monitoring_events(days=14)
        if deleted:
            logger.info("Purged %s old monitoring event(s)", deleted)
    except Exception:
        logger.exception("Failed to send hourly monitoring report")


def seconds_until_next_hour_tehran() -> float:
    now = datetime.now(TEHRAN_TZ)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(30.0, (next_hour - now).total_seconds())
