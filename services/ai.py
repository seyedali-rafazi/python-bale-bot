# services/ai.py

import os
import io
import urllib.parse
import asyncio
import aiohttp
from dotenv import load_dotenv
from gtts import gTTS
from telethon import TelegramClient

load_dotenv()
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")

# تنظیمات Telethon
CHATGPT_BOT_USERNAME = os.getenv("CHATGPT_BOT_USERNAME")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("AI_SESSION_NAME", "SESSION_NAME")

chatbot_lock = asyncio.Lock()


async def ask_chatbot(text):
    """ارسال متن به ربات هوش مصنوعی از طریق Telethon با مدیریت وضعیت در حال تایپ/ادیت"""
    async with chatbot_lock:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return "⚠️ خطا: اکانت تلگرام سرور (یوزربات) لاگین نیست."

        try:
            # دستور سخت‌گیرانه برای عدم استفاده از تاریخچه
            prompt = (
                "این یک درخواست کاملاً مستقل است. به هیچ عنوان از پیام‌های قبلی به عنوان اطلاعات یا کانتکست استفاده نکن.\n"
                f"متن درخواست:\n{text}"
            )

            await client.send_message(CHATGPT_BOT_USERNAME, prompt)

            last_text = ""
            stable_count = 0

            # حلقه انتظار برای تکمیل پیام (حداکثر 40 بار چک کردن = حدود 2 دقیقه)
            for _ in range(40):
                await asyncio.sleep(3)
                messages = await client.get_messages(CHATGPT_BOT_USERNAME, limit=2)

                if not messages:
                    continue

                latest_msg = messages[0]

                if latest_msg.text and not latest_msg.out and not latest_msg.sticker:
                    current_text = latest_msg.text.strip()

                    if len(current_text) > 10:
                        # بررسی اینکه آیا متن دیگر تغییر نمی‌کند (پایان ادیت)
                        if current_text == last_text:
                            stable_count += 1
                        else:
                            stable_count = 0
                            last_text = current_text

                        # اگر 2 بار متوالی متن ثابت موند، یعنی پیام کامل شده است
                        if stable_count >= 2:
                            return current_text

            return "❌ زمان انتظار پایان یافت یا ربات مبدا پاسخ را کامل نکرد."

        except Exception as e:
            print(f"Error in telethon AI chat: {e}")
            return "❌ خطا در برقراری ارتباط با ربات هوش مصنوعی."
        finally:
            await client.disconnect()


async def perform_ocr(image_bytes: bytes):
    try:
        data = aiohttp.FormData()
        data.add_field("apikey", OCR_SPACE_API_KEY)
        data.add_field("language", "ara")
        data.add_field(
            "filename", image_bytes, filename="image.jpg", content_type="image/jpeg"
        )

        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.ocr.space/parse/image", data=data
            ) as response:
                result = await response.json()

        if result.get("IsErroredOnProcessing"):
            return "❌ خطا در پردازش تصویر توسط سرور OCR."

        parsed_results = result.get("ParsedResults")
        if parsed_results and len(parsed_results) > 0:
            text = parsed_results[0].get("ParsedText", "متنی یافت نشد.")
            return text if text.strip() else "❌ متنی در این تصویر تشخیص داده نشد."
        return "❌ ساختار پاسخ سرور نامعتبر بود."
    except asyncio.TimeoutError:
        return "❌ سرور پردازش متن زمان‌بر شد. لطفاً بعداً تلاش کنید."
    except Exception as e:
        return f"❌ خطا در ارتباط با سرور OCR."


def _sync_tts(text):
    lang = "fa" if any("\u0600" <= c <= "\u06ff" for c in text) else "en"
    tts = gTTS(text=text, lang=lang, slow=False)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp


async def text_to_speech(text):
    try:
        return await asyncio.to_thread(_sync_tts, text)
    except Exception as e:
        print(f"TTS Error: {e}")
        return None


async def generate_image(prompt):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    return io.BytesIO(image_bytes)
        return None
    except asyncio.TimeoutError:
        print("Image Gen Error: Timeout")
        return None
    except Exception as e:
        print(f"Image Gen Error: {e}")
        return None
