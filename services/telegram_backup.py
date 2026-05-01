import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.custom import Message

load_dotenv()


API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")
TARGET_BOT = "@Gozilla_bot"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def download_from_telegram_bot(youtube_url: str, download_dir="downloads") -> str:
    """
    ارسال لینک به ربات تلگرام، انتخاب کیفیت و دانلود فایل
    """
    await client.start()

    # اطمینان از وجود پوشه
    os.makedirs(download_dir, exist_ok=True)

    async with client.conversation(TARGET_BOT, timeout=300) as conv:
        # ۱. ارسال لینک به ربات
        await conv.send_message(youtube_url)

        # ۲. دریافت پاسخ اول (معمولاً دکمه‌های شیشه‌ای انتخاب کیفیت)
        response: Message = await conv.get_response()

        # ۳. کلیک روی اولین دکمه (یا می‌توانید بر اساس متن دکمه فیلتر کنید)
        if response.buttons:
            # فرض میکنیم دکمه اول بهترین کیفیت یا کیفیت پیش‌فرض است
            await response.click(0)
        else:
            return None  # ربات دکمه ای نداد

        # ۴. صبر برای دریافت فایل ویدیو
        # ربات های دانلودر معمولا بعد از کلیک، چند پیام وضعیت میدهند و بعد فایل را میفرستند
        # در اینجا منتظر اولین ویدیوی دریافتی می‌مانیم
        while True:
            video_msg = await conv.get_response()
            if video_msg.video or video_msg.document:
                # ۵. دانلود فایل در سرور
                file_path = os.path.join(download_dir, f"tg_backup_{video_msg.id}.mp4")
                await client.download_media(video_msg, file=file_path)
                return file_path
            elif "خطا" in video_msg.text or "error" in video_msg.text.lower():
                return None
