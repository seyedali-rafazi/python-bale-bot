# services/ai.py (فایل جدید)

import requests
import google.generativeai as genai
import os
from dotenv import load_dotenv
import urllib.parse
from gtts import gTTS

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")

# تنظیمات Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-flash-latest")
except Exception as e:
    print(f"Error configuring Gemini: {e}")


def ask_chatbot(text):
    try:
        response = model.generate_content(text)
        return response.text
    except Exception as e:
        return f"❌ خطایی در ارتباط با هوش مصنوعی رخ داد: {e}"


def perform_ocr(image_path):
    try:
        payload = {"apikey": OCR_SPACE_API_KEY, "language": "ara"}
        with open(image_path, "rb") as f:
            # بسیار مهم: اضافه شدن timeout برای جلوگیری از قفل شدن تردها
            res = requests.post(
                "https://api.ocr.space/parse/image",
                files={"filename": f},
                data=payload,
                timeout=25,
            )
        result = res.json()

        if result.get("IsErroredOnProcessing"):
            return "❌ خطا در پردازش تصویر توسط سرور OCR."

        parsed_results = result.get("ParsedResults")
        if parsed_results and len(parsed_results) > 0:
            text = parsed_results[0].get("ParsedText", "متنی یافت نشد.")
            return text if text.strip() else "❌ متنی در این تصویر تشخیص داده نشد."
        return "❌ ساختار پاسخ سرور نامعتبر بود."
    except requests.exceptions.Timeout:
        return "❌ سرور پردازش متن زمان‌بر شد. لطفاً بعداً تلاش کنید."
    except Exception as e:
        return f"❌ خطا در ارتباط با سرور OCR."


def text_to_speech(text, unique_id):
    try:
        lang = "fa" if any("\u0600" <= c <= "\u06ff" for c in text) else "en"
        tts = gTTS(text=text, lang=lang, slow=False)
        file_path = f"temp_audio_{unique_id}.mp3"
        tts.save(file_path)
        return file_path
    except Exception as e:
        print(f"TTS Error: {e}")
        return None


def generate_image(prompt, unique_id):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

        # بسیار مهم: اضافه شدن timeout
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            file_path = f"temp_image_{unique_id}.jpg"
            with open(file_path, "wb") as f:
                f.write(response.content)
            return file_path
        return None
    except requests.exceptions.Timeout:
        print("Image Gen Error: Timeout")
        return None
    except Exception as e:
        print(f"Image Gen Error: {e}")
        return None
