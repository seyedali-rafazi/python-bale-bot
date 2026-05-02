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


def main():
    # ساخت جداول دیتابیس در هنگام استارت شدن بات
    init_db()

    # ساخت اپلیکیشن با پشتیبانی از job_queue
    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .base_file_url("https://tapi.bale.ai/file/bot")
        .build()
    )

    # افزودن تسک پاکسازی پوشه (هر ۷۲۰۰ ثانیه یک بار اجرا می‌شود، اولین اجرا ۱۰ ثانیه بعد از استارت)
    if application.job_queue:
        application.job_queue.run_repeating(
            cleanup_old_downloads, interval=7200, first=10
        )

    # ثبت تمام هندلرها از پوشه handlers
    register_all_handlers(application)

    print("✅ ربات با معماری جدید با موفقیت راه‌اندازی شد...")
    application.run_polling()


if __name__ == "__main__":
    main()
