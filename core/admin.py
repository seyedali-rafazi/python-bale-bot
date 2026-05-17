# core/admin.py


from telegram import Update
from telegram.ext import ContextTypes
from core.database import (
    get_total_users,
    set_vip,
    get_all_users,
    get_total_vip_users,
    reset_user_limits,
    add_vip_time_to_all,
    set_vip_expire_date,
    get_full_user_info,
    give_5gb_to_existing_vips,
)
import os
from dotenv import load_dotenv
import asyncio
import aiosqlite
from core.database import DB_NAME
from core.database import get_setting, set_setting
from datetime import datetime


load_dotenv()
# آیدی عددی ادمین را در فایل .env قرار دهید
ADMIN_ID = os.getenv("ADMIN_ID")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    total_users = await get_total_users()
    vip_users = await get_total_vip_users()
    normal_users = total_users - vip_users

    await update.message.reply_text(
        f"📊 **آمار ربات:**\n\n"
        f"تعداد کل کاربران: $ {total_users} $ نفر\n"
        f"کاربران عادی: $ {normal_users} $ نفر\n"
        f"کاربران VIP: $ {vip_users} $ نفر"
    )


async def cmd_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/setvip 123456789 1` برای فعال کردن\n`/setvip 123456789 0` برای غیرفعال کردن"
        )
        return

    target_user = context.args[0]
    status = int(context.args[1])

    await set_vip(target_user, status)
    status_text = "VIP شد 🌟" if status == 1 else "از VIP خارج شد ❌"

    await update.message.reply_text(f"✅ کاربر {target_user} {status_text}")


async def cmd_setexpire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n"
            "`/setexpire 123456789 27` - مجوز VIP برای 27 روز دیگر"
        )
        return

    target_user = context.args[0]
    try:
        days = int(context.args[1])
        if days < 1:
            await update.message.reply_text("❌ تعداد روز باید بیشتر از صفر باشد.")
            return
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح برای روز‌ها وارد کنید.")
        return

    success, expire_dt = await set_vip_expire_date(target_user, days)

    if success:
        await update.message.reply_text(
            f"✅ کاربر {target_user} VIP برای {days} روز دیگر شد.\n"
            f"تاریخ انقضا: {expire_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        await update.message.reply_text("❌ خطا در تنظیم VIP.")


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/userinfo 123456789`"
        )
        return

    target_user = context.args[0]
    user_data = await get_full_user_info(target_user)

    if not user_data:
        await update.message.reply_text(f"❌ کاربر {target_user} یافت نشد.")
        return

    # Parse the data
    (
        user_id,
        username,
        is_vip,
        join_date,
        vip_expire_date,
        yt_count,
        yt_date,
        music_count,
        music_date,
        pinterest_count,
        pinterest_date,
        tt_dl_count,
        tt_dl_date,
        tt_exp_count,
        tt_exp_date,
        gh_count,
        gh_date,
    ) = user_data

    # Format VIP status
    vip_status = "✅ VIP" if is_vip == 1 else "❌ عادی"

    # Format expire date
    if vip_expire_date:
        try:
            expire_dt = datetime.fromisoformat(vip_expire_date)
            now = datetime.now()
            if expire_dt > now:
                remaining = (expire_dt - now).days
                expire_text = f"{expire_dt.strftime('%Y-%m-%d %H:%M:%S')}\n({remaining} روز باقی مانده)"
            else:
                expire_text = f"{expire_dt.strftime('%Y-%m-%d %H:%M:%S')}\n(منقضی شده)"
        except:
            expire_text = vip_expire_date
    else:
        expire_text = "بدون تاریخ انقضا"

    info_text = f"""
📋 **اطلاعات کاربر {target_user}**

👤 نام کاربری: {username if username else "تعیین نشده"}
📱 شناسه: {user_id}
🎯 وضعیت: {vip_status}
📅 تاریخ انقضای VIP: {expire_text}
📝 تاریخ عضویت: {join_date if join_date else "نامشخص"}

📊 **آمار استفاده:**

🎬 یوتیوب:
   ├─ دانلود‌ها: {yt_count}
   └─ آخرین استفاده: {yt_date if yt_date else "هرگز"}

🎵 موسیقی:
   ├─ دانلود‌ها: {music_count}
   └─ آخرین استفاده: {music_date if music_date else "هرگز"}

📌 Pinterest:
   ├─ دانلود‌ها: {pinterest_count}
   └─ آخرین استفاده: {pinterest_date if pinterest_date else "هرگز"}

🎭 TikTok (دانلود):
   ├─ دانلود‌ها: {tt_dl_count}
   └─ آخرین استفاده: {tt_dl_date if tt_dl_date else "هرگز"}

🎭 TikTok (Export):
   ├─ Export‌ها: {tt_exp_count}
   └─ آخرین استفاده: {tt_exp_date if tt_exp_date else "هرگز"}

💻 GitHub:
   ├─ دانلود‌ها: {gh_count}
   └─ آخرین استفاده: {gh_date if gh_date else "هرگز"}
"""

    await update.message.reply_text(info_text)


async def cmd_messageuser(update, context):
    chat_id = str(update.effective_chat.id)
    if (
        chat_id != ADMIN_ID
    ):  # فرض بر این است که ADMIN_ID در این فایل ایمپورت یا تعریف شده است
        return

    # دریافت کل متن پیام ارسال شده توسط ادمین
    text = update.message.text

    # جدا کردن دستور (/messageuser) از متن اصلی
    parts = text.split(maxsplit=1)

    # بررسی اینکه آیا بعد از دستور، متنی هم نوشته شده است یا خیر
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ متن پیام را وارد کنید.\nمثال:\n`/messageuser سلام کاربران عزیز`"
        )
        return

    # قسمت دوم (ایندکس 1) شامل تمام متن همراه با اینترها است
    message_text = parts[1]
    users = await get_all_users()

    await update.message.reply_text(
        f"⏳ در حال ارسال پیام به $ {len(users)} $ کاربر..."
    )

    success = 0
    fail = 0

    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text)
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # جلوگیری از اسپم

    await update.message.reply_text(
        f"✅ ارسال به پایان رسید!\nموفق: $ {success} $\nناموفق: $ {fail} $"
    )


async def cmd_reset_limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_NAME) as conn:
        # صفر کردن تعداد دفعات استفاده برای همه کاربران
        await conn.execute(
            "UPDATE users SET yt_count = 0, music_count = 0, pinterest_count = 0"
        )
        # در صورت نیاز به پاک کردن جدول لاگ مصرف روزانه
        # await conn.execute("DELETE FROM usage_stats")
        await conn.commit()

    await update.message.reply_text("✅ محدودیت‌های تمامی کاربران با موفقیت ریست شد.")


async def cmd_toggle_yt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    # دریافت وضعیت فعلی
    current_status = await get_setting("youtube_enabled", "1")

    # تغییر وضعیت
    new_status = "0" if current_status == "1" else "1"
    await set_setting("youtube_enabled", new_status)

    status_text = "فعال ✅" if new_status == "1" else "غیرفعال ❌"
    await update.message.reply_text(f"وضعیت دانلودر یوتیوب: {status_text}")


async def cmd_resetuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال:\n`/resetuser 123456789`"
        )
        return

    target_user = context.args[0]

    await reset_user_limits(target_user)

    await update.message.reply_text(
        f"✅ محدودیت‌های کاربر $ {target_user} $ با موفقیت ریست شد."
    )


async def cmd_addvip_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ فرمت اشتباه است. مثال برای اضافه کردن ۵ روز:\n`/addvipall 5`"
        )
        return

    try:
        days = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح وارد کنید.")
        return

    updated_users = await add_vip_time_to_all(days)
    await update.message.reply_text(
        f"✅ با موفقیت $ {days} $ روز به اشتراک $ {updated_users} $ کاربر ویژه (پرو) اضافه شد."
    )


async def cmd_give_5gb_vips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    await update.message.reply_text(
        "⏳ در حال بررسی و اعمال حجم ابری برای کاربران VIP..."
    )

    try:
        await give_5gb_to_existing_vips()
        await update.message.reply_text(
            "✅ ۵۰۰۰ مگابایت فضای ابری با موفقیت به کاربران VIP قدیمی که حجم نداشتند اضافه شد."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطایی رخ داد:\n`{str(e)}`")
