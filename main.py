# main.py

import logging
from telegram.ext import ApplicationBuilder
from config import BALE_TOKEN
from handlers import register_all_handlers

# تنظیمات لاگ‌گیری
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    # ساخت اپلیکیشن
    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .build()
    )

    # ثبت تمام هندلرها از پوشه handlers
    register_all_handlers(application)

    print("✅ ربات با معماری جدید با موفقیت راه‌اندازی شد...")
    application.run_polling()

if __name__ == "__main__":
    main()
