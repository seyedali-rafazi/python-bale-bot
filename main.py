# main.py

import logging
from telegram.ext import ApplicationBuilder, MessageHandler, filters
from config import BALE_TOKEN
import handlers

# تنظیمات لاگ‌گیری برای رفع خطاهای احتمالی
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    # ساخت اپلیکیشن با توکن و آدرس پایه بله
    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .build()
    )

    # اتصال پردازشگر پیام‌ها به تمام پیام‌های متنی
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handlers.handle_message)
    command_handler = MessageHandler(filters.COMMAND, handlers.handle_command)
    
    application.add_handler(message_handler)
    application.add_handler(command_handler)

    print("✅ ربات بله با موفقیت راه‌اندازی شد...")
    application.run_polling()

if __name__ == "__main__":
    main()
