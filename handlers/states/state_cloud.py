# handlers/states/state_cloud.py

from telegram import Update, InputFile
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ChatAction
import asyncio
import os
import re
from core.state_manager import set_state, clear_state
from core.task_utils import async_temp_dir, get_file_size_async
from core.database import (
    get_available_cloud_mb,
    reserve_cloud_quota,
    release_cloud_quota,
    record_cloud_upload,
    get_cloud_usage_stats,
    log_upload_success,
)
from services.parspack_s3 import async_upload_to_s3_with_key, upload_to_s3_with_key
from services.rate_limiter import user_action_lock


WAIT_FOR_FILE = 1


async def start_cloud_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start cloud file upload process"""
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass

    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return ConversationHandler.END

    user_id = str(chat.id)
    set_state(user_id, "cloud_upload")

    try:
        cloud_stats = await get_cloud_usage_stats(user_id)
        if not cloud_stats:
            await msg.reply_text("❌ اطلاعات حساب ابری یافت نشد. لطفاً ابتدا /start را بزنید.")
            return ConversationHandler.END

        available_mb = cloud_stats["total_quota"] - cloud_stats["used_quota"]
        available_gb = available_mb / 1024

        if available_mb <= 0:
            await msg.reply_text(
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

        await msg.reply_text(upload_text, parse_mode="Markdown")
        return WAIT_FOR_FILE

    except Exception as e:
        print(f"Error starting cloud upload: {e}")
        await msg.reply_text("❌ خطایی در شروع آپلود رخ داد.")
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

        async with user_action_lock(user_id, "cloud_upload", timeout_sec=60) as acquired:
            if not acquired:
                await update.message.reply_text("⏳ آپلود قبلی شما هنوز در حال انجام است. لطفاً صبر کنید.")
                return WAIT_FOR_FILE

            # Quick pre-check before downloading from Bale
            available_mb = await get_available_cloud_mb(user_id)
            if available_mb is None or file_size_mb > available_mb:
                await update.message.reply_text(
                    "❌ فضای کافی برای آپلود این فایل وجود ندارد!\n\n"
                    f"حجم فایل: {file_size_mb:.2f} MB\n"
                    f"فضای در دسترس: {available_mb if available_mb is not None else 0:.2f} MB"
                )
                return WAIT_FOR_FILE

            progress_msg = await update.message.reply_text("⏳ در حال آپلود فایل به سرور ابری...")

            safe_name = os.path.basename(file_name)
            safe_name = re.sub(r"[^\w.\-]", "_", safe_name) or "upload.bin"
            file = await context.bot.get_file(file_obj.file_id)

            download_link = None
            s3_key = None
            actual_size_mb = file_size_mb
            reserved = False
            async with async_temp_dir(prefix="cloud_up_") as tmp_dir:
                temp_file_path = os.path.join(tmp_dir, safe_name)
                await file.download_to_drive(temp_file_path)
                actual_size_mb = round(
                    (await get_file_size_async(temp_file_path)) / (1024 * 1024), 2
                )
                reserved = await reserve_cloud_quota(user_id, actual_size_mb)
                if not reserved:
                    avail_now = await get_available_cloud_mb(user_id)
                    await progress_msg.edit_text(
                        "❌ فضای کافی برای آپلود این فایل وجود ندارد!\n\n"
                        f"حجم فایل: {actual_size_mb:.2f} MB\n"
                        f"فضای در دسترس: {avail_now if avail_now is not None else 0:.2f} MB"
                    )
                    return WAIT_FOR_FILE

                try:
                    # Upload to S3 under bounded concurrency so multipart threads never saturate executor
                    download_link, s3_key = await async_upload_to_s3_with_key(
                        temp_file_path,
                        f"{user_id}/{safe_name}",
                        upload_fn=upload_to_s3_with_key,
                    )
                except Exception:
                    await release_cloud_quota(user_id, actual_size_mb)
                    raise

            if download_link:
                # Save file record (quota already reserved atomically)
                await record_cloud_upload(
                    user_id,
                    safe_name,
                    actual_size_mb,
                    download_link,
                    s3_key=s3_key,
                    quota_reserved=True,
                )

                # Compute remaining space from already-fetched available_mb without extra COUNT(*) query
                available_gb = max(0.0, available_mb - actual_size_mb) / 1024

                success_text = f"""
✅ **آپلود موفق**

📄 نام فایل: **{safe_name}**
💾 حجم: **{actual_size_mb:.2f} MB**
🔗 لینک دانلود: [دریافت]({download_link})

⚡ فضای در دسترس: **{available_gb:.2f} GB**

فایل شما در ابری ذخیره شد. می‌توانید این لینک را اشتراک‌گذاری کنید.
                """

                await progress_msg.edit_text(success_text, parse_mode="Markdown")
                await log_upload_success("cloud", user_id)
            else:
                if reserved:
                    await release_cloud_quota(user_id, actual_size_mb)
                await progress_msg.edit_text("❌ خطایی در آپلود فایل رخ داد. دوباره تلاش کنید.")
        
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
