# core/admin.py

from telegram import Update
from telegram.ext import ContextTypes
from core.database import get_total_users, set_vip, get_all_users
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()
# آیدی عددی ادمین را در فایل .env قرار دهید
ADMIN_ID = os.getenv("ADMIN_ID")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return  # فقط ادمین میتواند این دستور را اجرا کند

    total_users = get_total_users()
    await update.message.reply_text(
        f"📊 **آمار ربات:**\n\nتعداد کل کاربران: $ {total_users} $ نفر"
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
