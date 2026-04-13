# translator.py

from deep_translator import GoogleTranslator
from config import PROXY

def translate_text(source_lang, target_lang, text):
    """ترجمه متن با استفاده از مترجم گوگل"""
    try:
        # تنظیم پراکسی (اگر در config.py وجود داشته باشد)
        proxies = {
            "http": PROXY,
            "https": PROXY
        } if PROXY else None

        # اگر کاربر en:fa زد، باید به فرمت درک‌پذیر کتابخانه تبدیل شود
        # اگر کلمه 'auto' بود، زبان مبدا خودکار تشخیص داده می‌شود
        translator = GoogleTranslator(source=source_lang, target=target_lang, proxies=proxies)
        translated = translator.translate(text)
        
        return translated
    except Exception as e:
        print(f"Translation Error: {e}")
        return "❌ خطا در ترجمه! لطفاً مطمئن شوید کد زبان‌ها (مثل fa و en) را درست وارد کرده‌اید."
