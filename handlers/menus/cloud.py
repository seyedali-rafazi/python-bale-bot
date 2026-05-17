# handlers/menus/cloud.py

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from telegram.ext import ContextTypes
from core.constants import (
    BTN_UPLOAD_TO_CLOUD,
    BTN_CLOUD_FILES,
    BTN_BUY_CLOUD,
    BTN_BUY_CLOUD_SIZE1,
    BTN_BUY_CLOUD_SIZE2,
    BTN_BUY_CLOUD_SIZE3,
    BTN_BUY_CLOUD_SIZE4,
    BTN_BACK,
)
from core.database import get_cloud_usage_stats, get_user_cloud_files
from core.state_manager import set_state
import os
from dotenv import load_dotenv

load_dotenv()
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")


async def btn_cloud_storage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display cloud storage main menu with usage info"""
    user_id = str(update.effective_chat.id)
    
    try:
        cloud_stats = await get_cloud_usage_stats(user_id)
        
        if cloud_stats:
            available_mb = cloud_stats["total_quota"] - cloud_stats["used_quota"]
            # Round to nearest 0.5 GB for cleaner display
            available_gb = round(available_mb / 1024 * 2) / 2
            total_gb = round(cloud_stats["total_quota"] / 1024 * 2) / 2
            used_gb = round(cloud_stats["used_quota"] / 1024 * 2) / 2
            
            # Create usage bar
            usage_percent = (cloud_stats["used_quota"] / cloud_stats["total_quota"] * 100) if cloud_stats["total_quota"] > 0 else 0
            filled = int((usage_percent / 100) * 10)
            bar = "█" * filled + "░" * (10 - filled)
            
            cloud_text = f"""
☁️ **منوی ذخیره‌سازی ابری**

📊 **آمار ذخیره‌سازی:**
📌 فایل‌های آپلود شده: **{cloud_stats['file_count']}** فایل
💾 حجم استفاده شده: **{used_gb:.1f} GB**
📈 حجم کل: **{total_gb:.1f} GB**
⚡ فضای در دسترس: **{available_gb:.1f} GB**

میزان استفاده: [{bar}] {usage_percent:.1f}%

لطفاً یک گزینه را انتخاب کنید:
            """
        else:
            cloud_text = "☁️ **منوی ذخیره‌سازی ابری**\n\nلطفاً یک گزینه را انتخاب کنید:"
        
        keyboard = [
            [InlineKeyboardButton("📤 آپلود فایل", callback_data="cloud_upload")],
            [InlineKeyboardButton("📂 فایل‌های من", callback_data="cloud_files")],
            [InlineKeyboardButton("🛒 خرید حجم اضافی", callback_data="cloud_buy_menu")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main_menu")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(cloud_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error in cloud storage menu: {e}")
        await update.message.reply_text("❌ خطایی در بارگذاری منوی ابری رخ داد.")


async def btn_buy_cloud_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show cloud storage packages available for purchase"""
    query = update.callback_query
    await query.answer()
    
    buy_cloud_text = """
🛒 **خریدگاه حجم ابری**

🎁 هر بسته خریداری شده به حجم موجود شما اضافه می‌شود:

🔸 **بسته 5 GB** - برای آپلود فایل‌های درمیانی
🔸 **بسته 10 GB** - برای استوری‌ها و ویدیوهای کوتاه
🔸 **بسته 20 GB** - برای ویدیوهای HD
🔸 **بسته 50 GB** - برای کالکشن‌های بزرگ

لطفاً بسته‌ای را انتخاب کنید:
    """
    
    keyboard = [
        [InlineKeyboardButton("5 GB", callback_data="cloud_buy_5gb")],
        [InlineKeyboardButton("10 GB", callback_data="cloud_buy_10gb")],
        [InlineKeyboardButton("20 GB", callback_data="cloud_buy_20gb")],
        [InlineKeyboardButton("50 GB", callback_data="cloud_buy_50gb")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="cloud_back")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(buy_cloud_text, reply_markup=reply_markup, parse_mode="Markdown")


async def btn_cloud_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's uploaded cloud files"""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_chat.id)
    
    try:
        cloud_files = await get_user_cloud_files(user_id)
        
        if not cloud_files or len(cloud_files) == 0:
            files_text = "📂 **فایل‌های من**\n\nشما هنوز فایلی آپلود نکرده‌اید."
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="cloud_back")]]
        else:
            files_text = "📂 **فایل‌های من**\n\n"
            files_text += f"تعداد فایل‌ها: **{len(cloud_files)}**\n\n"
            
            for idx, file_info in enumerate(cloud_files[:10], 1):  # Show last 10 files
                file_id, file_name, file_size_mb, download_link, upload_date = file_info
                files_text += f"{idx}. **{file_name}** ({file_size_mb} MB)\n"
                files_text += f"   📅 {upload_date}\n"
                files_text += f"   🔗 [دانلود](continue)\n\n"
            
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="cloud_back")]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(files_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error showing cloud files: {e}")
        await query.edit_message_text("❌ خطایی در بارگذاری فایل‌ها رخ داد.")


async def btn_buy_cloud_size(update: Update, context: ContextTypes.DEFAULT_TYPE, size_gb: int):
    """Handle cloud size purchase button click - show TOS and payment button"""
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception as e:
        print(f"Note: Could not answer callback (may be too old): {e}")
    
    # Store purchase info in context for payment handler
    context.user_data["cloud_purchase"] = size_gb
    
    # Show TOS for cloud storage purchase
    tos_text = f"""
📋 **قوانین و مقررات خریدگاه حجم ابری**

شما در حال خریدگاه **{size_gb} GB** حجم ابری هستید.

✅ **مزایا:**
• اضافه شدن {size_gb} گیگابایت به حجم موجود شما
• دسترسی دائم به فایل‌های آپلود شده
• لینک دانلود قابل اشتراک‌گذاری

⚠️ **توجه:**
• این حجم تا انتهای عمر حساب شما باقی می‌ماند
• وجه پرداختی قابل استرداد نیست
• حذف فایل، فضای ذخیره‌سازی را آزاد می‌کند

جهت تایید و پرداخت، دکمه زیر را لمس کنید:
    """
    
    keyboard = [[InlineKeyboardButton("✅ تایید و پرداخت", callback_data=f"accept_cloud_purchase_{size_gb}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(tos_text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Note: Could not edit message: {e}")
        # If edit fails, send as new message
        await context.bot.send_message(chat_id=update.effective_chat.id, text=tos_text, reply_markup=reply_markup, parse_mode="Markdown")
