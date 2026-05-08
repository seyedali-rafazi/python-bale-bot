# main.py
import logging
import asyncio
from telegram import Bot
from telegram.ext import Application, ApplicationBuilder, ContextTypes
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


load_dotenv()
BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_URL = os.getenv("BALE_URL")
BALE_LISTENING_PORT = os.getenv("BALE_LISTENING_PORT")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


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
            # Optionally, inform the user about the failure
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

    # روشن کردن هر دو کلاینت تلگرام (AI و Scihub)
    await startup_telethon_client()
    await startup_research_client()


async def post_shutdown(application: Application):
    logger.info("Running pre-shutdown tasks...")

    # خاموش کردن امن هر دو کلاینت
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
        .build()
    )

    if application.job_queue:
        application.job_queue.run_repeating(
            cleanup_old_downloads, interval=7200, first=10
        )

    register_all_handlers(application)
    logger.info("✅ ربات با صف دانلود و معماری بهینه راه‌اندازی شد...")
    PORT = int(os.environ.get("PORT", BALE_LISTENING_PORT))
    WEBHOOK_URL = f"{BALE_URL}/{BALE_TOKEN}"
    application.run_webhook(
        listen="0.0.0.0", port=PORT, url_path=BALE_TOKEN, webhook_url=WEBHOOK_URL
    )


if __name__ == "__main__":
    main()
