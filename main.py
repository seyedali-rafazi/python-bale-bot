# main.py

import logging
import asyncio
from telegram import Bot, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
)
from handlers import register_all_handlers
import os
import time
from dotenv import load_dotenv

# ایمپورت‌های مربوط به دیتابیس، صف دانلود و سرویس‌ها
from core.database import init_db, increment_book_download_count
from services.book.queue_manager import download_queue
from services.book.book_service import download_book_pdf

# === ایمپورت‌های جدید برای مدیریت چرخه عمر کلاینت Telethon ===
from services.ai_abstract import startup_telethon_client, shutdown_telethon_client
from services.research import startup_research_client, shutdown_research_client
from datetime import datetime, timezone


load_dotenv()
BALE_TOKEN = os.getenv("BALE_TOKEN")
# در حالت پولینگ نیازی به BALE_URL و PORT نیست

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# === تغییر جدید: تابع فیلتر پیام‌های قدیمی ===
async def ignore_old_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نادیده گرفتن پیام‌هایی که قبل از ران شدن ربات ارسال شده‌اند"""
    if update.message and update.message.date:
        now = datetime.now(timezone.utc)
        # اگر پیام برای بیشتر از ۶۰ ثانیه پیش بود، آن را پردازش نکن
        if (now - update.message.date).total_seconds() > 60:
            logger.info("Ignoring old message...")
            raise ApplicationHandlerStop()  # متوقف کردن چرخه آپدیت برای این پیام


async def cleanup_old_downloads(context: ContextTypes.DEFAULT_TYPE):
    """پاکسازی فایل‌های دانلودی قدیمی‌تر از ۲ ساعت."""
    now = time.time()
    directories_to_clean = ["downloads", "ig_downloads"]
    for directory in directories_to_clean:
        if not os.path.exists(directory):
            continue
        for f in os.listdir(directory):
            file_path = os.path.join(directory, f)
            if os.path.isfile(file_path):
                if os.stat(file_path).st_mtime < now - 7200:
                    try:
                        os.remove(file_path)
                        logger.info(f"🗑️ Cleaned up old file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error cleaning file {file_path}: {e}")


async def download_worker(bot: Bot):
    """پردازشگر صف دانلود: درخواست‌ها را از صف برداشته و پردازش می‌کند."""
    logger.info("✅ Download worker started and is waiting for jobs.")
    while True:
        try:
            job = await download_queue.get()
            chat_id = job.get("chat_id")
            book_data = job.get("book_data")
            status_msg_id = job.get("status_msg_id")

            logger.info(
                f"Processing download for chat {chat_id}, book: {book_data.get('title')}"
            )
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text="⏳ در حال دانلود فایل از سرور... این مرحله ممکن است کمی طول بکشد.",
            )

            pdf_file = await download_book_pdf(book_data)

            if pdf_file:
                increment_book_download_count(chat_id)
                caption = f"📕 **عنوان:** {book_data['title']}\n👤 **نویسنده:** {book_data['author']}"
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text="✅ دانلود کامل شد. در حال ارسال فایل برای شما...",
                )
                await bot.send_document(
                    chat_id=chat_id,
                    document=pdf_file,
                    caption=caption,
                    parse_mode="Markdown",
                )
                await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text="❌ متاسفانه در دانلود این کتاب مشکلی پیش آمد. لطفا دوباره تلاش کنید.",
                )
        except Exception as e:
            logger.error(f"Error in download worker for chat {job.get('chat_id')}: {e}")
            if job and job.get("chat_id") and job.get("status_msg_id"):
                await bot.edit_message_text(
                    chat_id=job.get("chat_id"),
                    message_id=job.get("status_msg_id"),
                    text="❌ یک خطای غیرمنتظره در پردازش درخواست شما رخ داد. لطفا بعدا تلاش کنید.",
                )
        finally:
            download_queue.task_done()


async def post_init(application: Application):
    logger.info("Running post-initialization tasks...")
    asyncio.create_task(download_worker(application.bot))

    await startup_telethon_client()
    await startup_research_client()


async def post_shutdown(application: Application):
    logger.info("Running pre-shutdown tasks...")
    await shutdown_telethon_client()
    await shutdown_research_client()


def main():
    init_db()

    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .base_file_url("https://tapi.bale.ai/file/bot")
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    if application.job_queue:
        application.job_queue.run_repeating(
            cleanup_old_downloads, interval=7200, first=10
        )

    # === تغییر جدید: ثبت هندلر فیلتر پیام‌های قدیمی قبل از سایر هندلرها (group=-1) ===
    application.add_handler(TypeHandler(Update, ignore_old_messages), group=-1)

    register_all_handlers(application)
    logger.info("✅ ربات در حالت پولینگ (Polling) راه‌اندازی شد...")

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
