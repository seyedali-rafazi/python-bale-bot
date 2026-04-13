# services/translator.py

from deep_translator import GoogleTranslator
import os
from dotenv import load_dotenv

load_dotenv() 
PROXY = os.getenv("PROXY")

def translate_text(source_lang, target_lang, text):
    try:
        proxies = {"http": PROXY, "https": PROXY} if PROXY else None
        translator = GoogleTranslator(source=source_lang, target=target_lang, proxies=proxies)
        return translator.translate(text)
    except Exception as e:
        print(f"Translation Error: {e}")
        return "❌ خطا در ترجمه! لطفاً مطمئن شوید کد زبان‌ها را درست وارد کرده‌اید."
