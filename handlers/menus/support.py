from datetime import datetime

from telegram import (
    Update,
)
from telegram.ext import ContextTypes

from core.constants import BALE_SUPPORT_URL
from core.database import (
    get_gh_downloads,
    get_music_downloads,
    get_pinterest_downloads,
    get_tt_downloads,
    get_tt_explores,
    get_user_info,
    get_yt_downloads,
)


async def btn_profile_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_info = get_user_info(user_id)

    if not user_info:
        await update.message.reply_text(
            "❌ اطلاعات شما یافت نشد. لطفاً دستور /start را ارسال کنید."
        )
        return

    username, is_vip, join_date, vip_expire_date = user_info

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
                    vip_duration_text = f"\n⏳ اعتبار اشتراک: {remaining_days} روز"
                else:
                    vip_duration_text = "\n⏳ اعتبار اشتراک: منقضی شده"

            except Exception as e:
                print(f"Error parsing date for user {user_id}: {e}")
                vip_duration_text = "\n⏳ اعتبار اشتراک: نامشخص (خطا)"

    yt_count = get_yt_downloads(user_id)
    music_count = get_music_downloads(user_id)
    pinterest_count = get_pinterest_downloads(user_id)
    tt_dl_count = get_tt_downloads(user_id)
    tt_exp_count = get_tt_explores(user_id)
    gh_count = get_gh_downloads(user_id)

    yt_limit = "20" if is_vip == 1 else "1"
    music_limit = "20" if is_vip == 1 else "6"
    pinterest_limit = "30" if is_vip == 1 else "2"
    tt_dl_limit = "15" if is_vip == 1 else "1"
    tt_exp_limit = "10" if is_vip == 1 else "1"
    gh_limit = "20" if is_vip == 1 else "2"

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
• تیک‌تاک | اکسپلور: $ {tt_exp_count} / {tt_exp_limit} $
• گیت‌هاب | دانلود: $ {gh_count} / {gh_limit} $
"""

    await update.message.reply_text(profile_text.strip(), parse_mode="Markdown")
