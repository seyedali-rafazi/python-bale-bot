# services/ai.py (فایل جدید)

import requests
import google.generativeai as genai
import os
from dotenv import load_dotenv
import urllib.parse 
from gtts import gTTS

load_dotenv() # خواندن فایل .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
PROXY = os.getenv("PROXY")


# تنظیمات Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-flash-latest')
except Exception as e:
    print(f"Error configuring Gemini: {e}")

def ask_chatbot(text):
    try:
        # اگر در ایران هستید ممکن است برای جمنای به پراکسی نیاز داشته باشید
        # در غیر این صورت روی سرورهای خارجی به درستی کار می‌کند
        response = model.generate_content(text)
        return response.text
    except Exception as e:
        return f"❌ خطایی در ارتباط با هوش مصنوعی رخ داد: {e}"

def perform_ocr(image_path):
    try:
        # ara برای تشخیص حروف فارسی/عربی مناسب است
        payload = {'apikey': OCR_SPACE_API_KEY, 'language': 'ara'} 
        with open(image_path, 'rb') as f:
            res = requests.post(
                'https://api.ocr.space/parse/image',
                files={'filename': f},
                data=payload
            )
        result = res.json()
        
        if result.get('IsErroredOnProcessing'):
            return "❌ خطا در پردازش تصویر توسط سرور OCR."
            
        parsed_results = result.get('ParsedResults')
        if parsed_results and len(parsed_results) > 0:
            text = parsed_results[0].get('ParsedText', 'متنی یافت نشد.')
            return text if text.strip() else "❌ متنی در این تصویر تشخیص داده نشد."
        return "❌ ساختار پاسخ سرور نامعتبر بود."
    except Exception as e:
        return f"❌ خطا در ارتباط با سرور OCR: {e}"

def text_to_speech(text, chat_id):
    try:
        # تشخیص زبان (ساده: اگر حروف فارسی داشت، فارسی)
        lang = 'fa' if any('\u0600' <= c <= '\u06FF' for c in text) else 'en'
        tts = gTTS(text=text, lang=lang, slow=False)
        file_path = f"temp_audio_{chat_id}.mp3"
        tts.save(file_path)
        return file_path
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

def generate_image(prompt, chat_id):
    try:
        # استفاده از API رایگان pollinations
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        response = requests.get(url)
        if response.status_code == 200:
            file_path = f"temp_image_{chat_id}.jpg"
            with open(file_path, 'wb') as f:
                f.write(response.content)
            return file_path
        return None
    except Exception as e:
        print(f"Image Gen Error: {e}")
        return None