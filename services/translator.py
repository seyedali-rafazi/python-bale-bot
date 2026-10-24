# services/translator.py

import os
import logging
from dotenv import load_dotenv
from deep_translator import GoogleTranslator, MyMemoryTranslator

logger = logging.getLogger(__name__)

load_dotenv()
PROXY = os.getenv("PROXY")
# If no proxy is provided in .env, explicitly pass empty strings to avoid inheriting broken system proxies
proxies = {"http": PROXY, "https": PROXY} if PROXY else {"http": "", "https": ""}

# Cached translator instances
cached_translators = {
    ("fa", "en"): GoogleTranslator(source="fa", target="en", proxies=proxies),
    ("en", "fa"): GoogleTranslator(source="en", target="fa", proxies=proxies),
}

_MYMEMORY_LANG_MAP = {
    "fa": "fa-IR",
    "en": "en-GB",
    "ar": "ar-SA",
    "fr": "fr-FR",
    "de": "de-DE",
    "es": "es-ES",
    "ru": "ru-RU",
    "tr": "tr-TR",
}


def _lang_code_mymemory(lang: str) -> str:
    return _MYMEMORY_LANG_MAP.get(lang.lower(), lang)


def translate_text(source_lang: str, target_lang: str, text: str) -> str:
    if not text or not text.strip():
        return "❌ لطفاً متنی برای ترجمه وارد کنید."

    clean_text = text.strip()

    # 1. Try Google Translator
    try:
        translator = cached_translators.get((source_lang, target_lang))
        if not translator:
            translator = GoogleTranslator(
                source=source_lang, target=target_lang, proxies=proxies
            )
        result = translator.translate(clean_text)
        if result and not str(result).startswith("Server Error:"):
            return result
        logger.warning("Google translator returned server error or empty result, trying fallback...")
    except Exception as e:
        logger.warning("Google translation failed: %s, trying fallback...", e)

    # 2. Fallback to MyMemory Translator
    try:
        s = _lang_code_mymemory(source_lang)
        t = _lang_code_mymemory(target_lang)
        fallback_translator = MyMemoryTranslator(source=s, target=t, proxies=proxies)
        result = fallback_translator.translate(clean_text)
        if result and not str(result).startswith("MYMEMORY WARNING:"):
            return result
    except Exception as e:
        logger.error("MyMemory fallback translation failed: %s", e)

    return "❌ خطا در ترجمه! لطفاً کمی بعد دوباره تلاش کنید."
