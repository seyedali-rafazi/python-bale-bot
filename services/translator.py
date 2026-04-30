# services/translator.py

from deep_translator import GoogleTranslator
import os
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")
# تعریف پروکسی فقط یکبار در زمان لود شدن ماژول
proxies = {"http": PROXY, "https": PROXY} if PROXY else None

# کش (Cache) کردن مترجم‌ها برای جلوگیری از ساخت مجدد آنها در هر درخواست کاربر
cached_translators = {
    ("fa", "en"): GoogleTranslator(source="fa", target="en", proxies=proxies),
    ("en", "fa"): GoogleTranslator(source="en", target="fa", proxies=proxies),
}


def translate_text(source_lang, target_lang, text):
    try:
        # استفاده از مترجمِ از قبل آماده شده
        translator = cached_translators.get((source_lang, target_lang))
        if not translator:
            # در صورتی که زبان جدیدی بعدا اضافه کردید
            translator = GoogleTranslator(
                source=source_lang, target=target_lang, proxies=proxies
            )

        return translator.translate(text)
    except Exception as e:
        print(f"Translation Error: {e}")
        return "❌ خطا در ترجمه! ممکن است سرور گوگل موقتاً پاسخگو نباشد."
