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


def _format_section_block(counts: dict[str, int]) -> list[str]:
    lines: list[str] = []
    total = 0
    for section in ALL_SECTIONS:
        count = counts.get(section, 0)
        if count <= 0:
            continue
        total += count
        lines.append(f"  {SECTION_LABELS[section]}: {count}")
    if total == 0:
        lines.append("  — فعالیتی ثبت نشده")
    else:
        lines.append(f"  📦 جمع: {total}")
    return lines


def build_monitoring_report_text(data: dict, total_users: int, vip_users: int) -> str:
    now_label = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M")
    normal_users = total_users - vip_users

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
        "✅ آپلود / پاسخ موفق — این ساعت",
        *_format_section_block(data["hour_section_counts"]),
        "",
        f"💬 کل پاسخ‌های موفق این ساعت: {data['hour_responses']}",
        "",
        "📈 مجموع موفق امروز (از نیمه‌شب)",
        *_format_section_block(data["today_section_counts"]),
        "",
        f"💬 کل پاسخ‌های موفق امروز: {data['today_responses']}",
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
