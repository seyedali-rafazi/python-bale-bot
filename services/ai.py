# services/ai.py (فایل جدید)

import os
import io
import urllib.parse
import asyncio
import aiohttp
import google.generativeai as genai
from dotenv import load_dotenv
from gtts import gTTS

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-flash-latest")
except Exception as e:
    print(f"Error configuring Gemini: {e}")


async def ask_chatbot(text):
    try:
        # استفاده از متد async خود جمنای
        response = await model.generate_content_async(text)
        return response.text
    except Exception as e:
        return f"❌ خطایی در ارتباط با هوش مصنوعی رخ داد: {e}"


async def perform_ocr(image_bytes: bytes):
    try:
        data = aiohttp.FormData()
        data.add_field("apikey", OCR_SPACE_API_KEY)
        data.add_field("language", "ara")
        # ارسال مستقیم بایت‌ها بدون نیاز به فایل فیزیکی
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
    # این تابع چون gTTS سینک است، در ترد جداگانه اجرا می‌شود
    lang = "fa" if any("\u0600" <= c <= "\u06ff" for c in text) else "en"
    tts = gTTS(text=text, lang=lang, slow=False)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp


async def text_to_speech(text):
    try:
        # ساخت فایل در حافظه رم به جای هارد دیسک
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
                    # برگرداندن عکس در حافظه رم
                    return io.BytesIO(image_bytes)
        return None
    except asyncio.TimeoutError:
        print("Image Gen Error: Timeout")
        return None
    except Exception as e:
        print(f"Image Gen Error: {e}")
        return None
