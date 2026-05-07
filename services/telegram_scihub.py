# services/telegram_scihub.py

import os
import asyncio
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")
SCIHUB_BOT_USERNAME = os.getenv("SCIHUB_BOT_USERNAME")

# آیدی ربات سای‌هاب در تلگرام (می‌توانید ربات‌های جایگزین هم تست کنید)


async def download_pdf_via_telegram(doi: str) -> str:
    """
    دی‌او‌آی را به ربات تلگرام می‌فرستد و فایل دانلود شده را برمی‌گرداند
    """
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()  # در اولین اجرا، شماره موبایل و کد تایید می‌خواهد

    downloaded_file_path = None

    try:
        # ارسال DOI به ربات سای‌هاب در تلگرام
        await client.send_message(SCIHUB_BOT_USERNAME, doi)

        # چند ثانیه صبر می‌کنیم تا ربات فایل را بفرستد (بسته به سرعت ربات تلگرام)
        await asyncio.sleep(5)

        # دریافت آخرین پیام‌های ربات
        messages = await client.get_messages(SCIHUB_BOT_USERNAME, limit=3)

        for msg in messages:
            if msg.file and msg.file.ext == ".pdf":
                # اگر فایل PDF بود، آن را دانلود کن
                print("PDF پیدا شد! در حال دانلود...")
                # مسیر ذخیره فایل روی سرور
                file_path = f"downloads/{doi.replace('/', '_')}.pdf"
                os.makedirs("downloads", exist_ok=True)

                await client.download_media(message=msg, file=file_path)
                downloaded_file_path = file_path
                break

    except Exception as e:
        print(f"Error in Telegram fetch: {e}")
    finally:
        await client.disconnect()

    return downloaded_file_path
