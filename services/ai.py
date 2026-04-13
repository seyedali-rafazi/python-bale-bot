# services/ai.py (فایل جدید)

import requests
import google.generativeai as genai
from config import GEMINI_API_KEY, OCR_SPACE_API_KEY, PROXY

# تنظیمات Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
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
