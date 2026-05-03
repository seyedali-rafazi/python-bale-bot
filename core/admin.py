# core/admin.py

from telegram import Update
from telegram.ext import ContextTypes
from core.database import (
    get_total_users,
    set_vip,
    get_all_users,
    get_total_vip_users,
    reset_user_limits,
)
import os
from dotenv import load_dotenv
import asyncio
import sqlite3
from core.database import DB_NAME
from core.database import get_setting, set_setting


load_dotenv()
# آیدی عددی ادمین را در فایل .env قرار دهید
ADMIN_ID = os.getenv("ADMIN_ID")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    total_users = get_total_users()
    vip_users = get_total_vip_users()
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

    set_vip(target_user, status)
    status_text = "VIP شد 🌟" if status == 1 else "از VIP خارج شد ❌"

    await update.message.reply_text(f"✅ کاربر {target_user} {status_text}")


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
    users = get_all_users()

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

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # صفر کردن تعداد دفعات استفاده برای همه کاربران

    cursor.execute(
        "UPDATE users SET yt_count = 0, music_count = 0, pinterest_count = 0"
    )

    # در صورت نیاز به پاک کردن جدول لاگ مصرف روزانه
    # cursor.execute("DELETE FROM usage_stats")

    conn.commit()
    conn.close()

    await update.message.reply_text("✅ محدودیت‌های تمامی کاربران با موفقیت ریست شد.")


async def cmd_toggle_yt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return

    # دریافت وضعیت فعلی
    current_status = get_setting("youtube_enabled", "1")

    # تغییر وضعیت
    new_status = "0" if current_status == "1" else "1"
    set_setting("youtube_enabled", new_status)

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

    reset_user_limits(target_user)

    await update.message.reply_text(
        f"✅ محدودیت‌های کاربر $ {target_user} $ با موفقیت ریست شد."
    )
