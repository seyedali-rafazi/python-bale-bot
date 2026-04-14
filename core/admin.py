from telegram import Update
from telegram.ext import ContextTypes
from core.database import get_total_users, set_vip
import os
from dotenv import load_dotenv

load_dotenv()
# آیدی عددی ادمین را در فایل .env قرار دهید
ADMIN_ID = os.getenv("ADMIN_ID") 

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return # فقط ادمین میتواند این دستور را اجرا کند
        
    total_users = get_total_users()
    await update.message.reply_text(f"📊 **آمار ربات:**\n\nتعداد کل کاربران: $ {total_users} $ نفر")

async def cmd_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_ID:
        return
        
    if len(context.args) < 2:
        await update.message.reply_text("❌ فرمت اشتباه است. مثال:\n`/setvip 123456789 1` برای فعال کردن\n`/setvip 123456789 0` برای غیرفعال کردن")
        return
        
    target_user = context.args[0]
    status = int(context.args[1])
    
    set_vip(target_user, status)
    status_text = "VIP شد 🌟" if status == 1 else "از VIP خارج شد ❌"
    
    await update.message.reply_text(f"✅ کاربر {target_user} {status_text}")
