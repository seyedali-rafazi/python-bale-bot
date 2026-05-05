# main.py


import logging
from telegram.ext import ApplicationBuilder, ContextTypes
from handlers import register_all_handlers
import os
import time
from dotenv import load_dotenv
from core.database import init_db

load_dotenv()
BALE_TOKEN = os.getenv("BALE_TOKEN")

# تنظیمات لاگ‌گیری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def cleanup_old_downloads(context: ContextTypes.DEFAULT_TYPE):
    """پاکسازی فایل‌هایی که بیشتر از ۲ ساعت (۷۲۰۰ ثانیه) در سرور مانده‌اند"""
    now = time.time()

    # لیست پوشه‌هایی که باید بررسی و پاکسازی شوند
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
                        print(f"🗑️ Cleaned up old file: {file_path}")
                    except Exception as e:
                        pass


async def main_async():
    # ساخت جداول دیتابیس در هنگام استارت شدن بات
    init_db()

    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .base_file_url("https://tapi.bale.ai/file/bot")
        .build()
    )

    # پاک کردن آپدیت‌های قدیمی قبل از شروع polling
    await application.bot.delete_webhook(drop_pending_updates=True)

    # job_queue
    if application.job_queue:
        application.job_queue.run_repeating(
            cleanup_old_downloads, interval=7200, first=10
        )

    register_all_handlers(application)

    print("✅ ربات با معماری جدید با موفقیت راه‌اندازی شد...")
    await application.run_polling()


def main():
    import asyncio

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
