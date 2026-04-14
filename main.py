# main.py

import logging
from telegram.ext import ApplicationBuilder
from handlers import register_all_handlers
import os
from dotenv import load_dotenv
from core.database import init_db

load_dotenv() 
BALE_TOKEN = os.getenv("BALE_TOKEN")

# تنظیمات لاگ‌گیری
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
     # ساخت جداول دیتابیس در هنگام استارت شدن بات 
    init_db() 

    # ساخت اپلیکیشن
    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .base_file_url("https://tapi.bale.ai/file/bot")
        .build()
    )

    # ثبت تمام هندلرها از پوشه handlers
    register_all_handlers(application)

    print("✅ ربات با معماری جدید با موفقیت راه‌اندازی شد...")
    application.run_polling()

if __name__ == "__main__":
    main()
