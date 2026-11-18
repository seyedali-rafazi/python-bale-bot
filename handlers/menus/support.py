from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes

from core.constants import BALE_SUPPORT_URL
from core.database import (
    get_user_profile_summary,
    archive_limit_period_label,
)
from core.limits import get_limit


async def btn_support_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💬 ارتباط با پشتیبانی در بله", url=BALE_SUPPORT_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "برای ارتباط با پشتیبانی، طرح پیشنهادات و گزارش مشکلات، روی دکمه زیر کلیک کنید:",
        reply_markup=reply_markup,
    )


async def btn_profile_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    summary = await get_user_profile_summary(user_id)

    if not summary:
        await update.message.reply_text(
            "❌ اطلاعات شما یافت نشد. لطفاً دستور /start را ارسال کنید."
        )
        return

    username = summary["username"]
    is_vip = summary["is_vip"]
    join_date = summary["join_date"]
    vip_expire_date = summary["vip_expire_date"]

    username_str = f"@{username}" if username else "ندارد"

    vip_status_text = "🆓 رایگان"
    vip_duration_text = ""

    if is_vip == 1:
        vip_status_text = "💎 ویژه (پرو)"
        if vip_expire_date:
            try:
                expire_dt = datetime.fromisoformat(vip_expire_date)
                now = datetime.now()

                if expire_dt > now:
                    remaining_time = expire_dt - now
                    remaining_days = remaining_time.days + 1
                    vip_duration_text = f"\n⏳ اعتبار اشتراک: $ {remaining_days} $ روز"
                else:
                    vip_duration_text = "\n⏳ اعتبار اشتراک: منقضی شده"

            except Exception as e:
                print(f"Error parsing date for user {user_id}: {e}")
                vip_duration_text = "\n⏳ اعتبار اشتراک: نامشخص (خطا)"

    yt_count = summary["yt_count"]
    music_count = summary["music_count"]
    pinterest_count = summary["pinterest_count"]
    tt_dl_count = summary["tt_dl_count"]
    gh_count = summary["gh_count"]
    web_count = summary["web_search_count"]
    ai_count = summary["ai_count"]
    arc_count = summary["arc_count"]
    tg_count = summary["tg_count"]

    yt_limit = get_limit("youtube_download", is_vip)
    music_limit = get_limit("music_download", is_vip)
    pinterest_limit = get_limit("pinterest_search", is_vip)
    tt_dl_limit = get_limit("tiktok_download", is_vip)
    gh_limit = get_limit("github_download", is_vip)
    web_limit = get_limit("web_search", is_vip)
    ai_limit = get_limit("ai_chat", is_vip)
    arc_limit = get_limit("yt_archive", is_vip)
    tg_limit = get_limit("telegram_download", is_vip)
    arc_period = archive_limit_period_label(is_vip)

    total_quota = summary["cloud_total_quota"]
    used_quota = summary["cloud_used_quota"]
    available_mb = round(total_quota - used_quota, 2)
    total_mb = round(total_quota, 2)
    used_mb = round(used_quota, 2)

    usage_percent = (used_quota / total_quota * 100) if total_quota > 0 else 0
    filled = int((usage_percent / 100) * 10)
    bar = "█" * filled + "░" * (10 - filled)

    cloud_info_text = f"""
☁️ **اطلاعات ذخیره‌سازی ابری:**
📌 فایل‌های آپلود شده: {summary["cloud_file_count"]} فایل
💾 حجم استفاده شده: {used_mb} MB
📈 حجم کل: {total_mb} MB
⚡ فضای در دسترس: {available_mb} MB
میزان استفاده: [{bar}] {usage_percent:.1f}%
"""

    profile_text = f"""
🪪 **مشخصات شما**
🆔 ایدی عددی: `{user_id}`
👤 یوزرنیم: {username_str}
📊 وضعیت اشتراک: {vip_status_text}{vip_duration_text}
📆 اولین استفاده: {join_date}

⏳ **مصرف امروز (به وقت ایران؛ ریست نیمه‌شب):**
• یوتیوب | دانلود: $ {yt_count} / {yt_limit} $
• موسیقی | دانلود: $ {music_count} / {music_limit} $
• پینترست | جستجو: $ {pinterest_count} / {pinterest_limit} $
• تیک‌تاک | دانلود: $ {tt_dl_count} / {tt_dl_limit} $
• گیت‌هاب | دانلود: $ {gh_count} / {gh_limit} $
• تلگرام | دریافت: $ {tg_count} / {tg_limit} $
• جستجوی وب | دانلود: $ {web_count} / {web_limit} $
• هوش مصنوعی | پرسش متنی: $ {ai_count} / {ai_limit} $ (فقط متن؛ ریست نیمه‌شب تهران)

📥 **کش یوتیوب (دریافت از آرشیو — {arc_period}):**
• $ {arc_count} / {arc_limit} $

{cloud_info_text}
"""

    await update.message.reply_text(profile_text.strip(), parse_mode="Markdown")
