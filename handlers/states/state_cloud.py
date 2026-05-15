# handlers/states/state_cloud.py

from telegram import Update, InputFile
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ChatAction
import os
from core.state_manager import set_state, clear_state
from core.database import (
    get_available_cloud_mb,
    reduce_cloud_storage,
    add_cloud_file,
    get_cloud_usage_stats,
)
from services.parspack_s3 import upload_to_s3


WAIT_FOR_FILE = 1


async def start_cloud_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start cloud file upload process"""
    user_id = str(update.effective_chat.id)
    set_state(user_id, "cloud_upload")
    
    try:
        cloud_stats = await get_cloud_usage_stats(user_id)
        available_mb = cloud_stats["total_quota"] - cloud_stats["used_quota"]
        available_gb = available_mb / 1024
        
        if available_mb <= 0:
            await update.message.reply_text(
                "❌ فضای ذخیره‌سازی شما پر است!\n\n"
                "🛒 برای اضافه کردن حجم، روی دکمه **خرید حجم اضافی** کلیک کنید."
            )
            return ConversationHandler.END
        
        upload_text = f"""
📤 **آپلود فایل به ابری**

فضای در دسترس: **{available_gb:.2f} GB**

لطفاً فایل خود را ارسال کنید.

⏱️ زمان انتظار: حداکثر 5 دقیقه
📏 حجم مجاز: حداکثر {available_mb} MB
📝 فرمت‌های پشتیبانی شده: تمام فرمت‌ها

برای لغو، /cancel را ارسال کنید.
        """
        
        await update.message.reply_text(upload_text, parse_mode="Markdown")
        return WAIT_FOR_FILE
        
    except Exception as e:
        print(f"Error starting cloud upload: {e}")
        await update.message.reply_text("❌ خطایی در شروع آپلود رخ داد.")
        return ConversationHandler.END


async def handle_cloud_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload to cloud storage"""
    user_id = str(update.effective_chat.id)
    
    try:
        # Check if a file was sent
        if not update.message.document and not update.message.video and not update.message.audio and not update.message.photo:
            await update.message.reply_text("❌ لطفاً یک فایل ارسال کنید.")
            return WAIT_FOR_FILE
        
        # Get file info
        if update.message.document:
            file_obj = update.message.document
            file_name = file_obj.file_name or "document"
        elif update.message.video:
            file_obj = update.message.video
            file_name = f"video_{file_obj.file_id[:10]}.mp4"
        elif update.message.audio:
            file_obj = update.message.audio
            file_name = file_obj.title or f"audio_{file_obj.file_id[:10]}.mp3"
        elif update.message.photo:
            file_obj = update.message.photo[-1]  # Get highest quality photo
            file_name = f"photo_{file_obj.file_id[:10]}.jpg"
        else:
            await update.message.reply_text("❌ فایلی پشتیبانی نشده.")
            return WAIT_FOR_FILE
        
        file_size_mb = (file_obj.file_size or 0) / (1024 * 1024)
        
        # Check available space
        available_mb = await get_available_cloud_mb(user_id)
        if available_mb is None or file_size_mb > available_mb:
            await update.message.reply_text(
                "❌ فضای کافی برای آپلود این فایل وجود ندارد!\n\n"
                f"حجم فایل: {file_size_mb:.2f} MB\n"
                f"فضای در دسترس: {available_mb:.2f} MB"
            )
            return WAIT_FOR_FILE
        
        # Show uploading progress
        progress_msg = await update.message.reply_text("⏳ در حال آپلود فایل به سرور ابری...")
        
        # Download file from Telegram
        file = await context.bot.get_file(file_obj.file_id)
        temp_file_path = f"/tmp/{user_id}_{file_name}"
        
        await file.download_to_drive(temp_file_path)
        
        # Upload to S3
        download_link = upload_to_s3(temp_file_path, f"{user_id}/{file_name}")
        
        if download_link:
            # Save to database
            await reduce_cloud_storage(user_id, file_size_mb)
            await add_cloud_file(user_id, file_name, file_size_mb, download_link)
            
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            # Get updated cloud stats
            cloud_stats = await get_cloud_usage_stats(user_id)
            available_gb = (cloud_stats["total_quota"] - cloud_stats["used_quota"]) / 1024
            
            success_text = f"""
✅ **آپلود موفق**

📄 نام فایل: **{file_name}**
💾 حجم: **{file_size_mb:.2f} MB**
🔗 لینک دانلود: [دریافت](continue)

⚡ فضای در دسترس: **{available_gb:.2f} GB**

فایل شما در ابری ذخیره شد. می‌توانید این لینک را اشتراک‌گذاری کنید.
            """
            
            await progress_msg.edit_text(success_text, parse_mode="Markdown")
        else:
            await progress_msg.edit_text("❌ خطایی در آپلود فایل رخ داد. دوباره تلاش کنید.")
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        
        clear_state(user_id)
        return ConversationHandler.END
        
    except Exception as e:
        print(f"Error uploading file to cloud: {e}")
        await update.message.reply_text(f"❌ خطایی در آپلود رخ داد: {str(e)}")
        clear_state(user_id)
        return ConversationHandler.END


async def cancel_cloud_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel cloud upload process"""
    user_id = str(update.effective_chat.id)
    clear_state(user_id)
    await update.message.reply_text("❌ آپلود لغو شد.")
    return ConversationHandler.END
