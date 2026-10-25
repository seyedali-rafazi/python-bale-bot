# services/translator.py

import os
import logging
from dotenv import load_dotenv
try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
except ImportError:
    GoogleTranslator = None
    MyMemoryTranslator = None

logger = logging.getLogger(__name__)

load_dotenv()
PROXY = os.getenv("PROXY")
# If no proxy is provided in .env, explicitly pass empty strings to avoid inheriting broken system proxies
proxies = {"http": PROXY, "https": PROXY} if PROXY else {"http": "", "https": ""}

# Cached translator instances
cached_translators = {}
if GoogleTranslator is not None:
    try:
        cached_translators = {
            ("fa", "en"): GoogleTranslator(source="fa", target="en", proxies=proxies),
            ("en", "fa"): GoogleTranslator(source="en", target="fa", proxies=proxies),
        }
    except Exception:
        cached_translators = {}


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

    # Check Redis Cache
    import hashlib
    text_hash = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
    cache_key = f"bale:cache:tr:{source_lang}:{target_lang}:{text_hash}"
    try:
        from services.redis_client import get_sync_redis
        sync_redis = get_sync_redis()
        if sync_redis is not None:
            cached_val = sync_redis.get(cache_key)
            if cached_val:
                return cached_val
    except Exception:
        pass

    translated_result = None

    # 1. Try Google Translator
    try:
        translator = cached_translators.get((source_lang, target_lang))
        if not translator:
            translator = GoogleTranslator(
                source=source_lang, target=target_lang, proxies=proxies
            )
        result = translator.translate(clean_text)
        if result and not str(result).startswith("Server Error:"):
            translated_result = result
        else:
            logger.warning("Google translator returned server error or empty result, trying fallback...")
    except Exception as e:
        logger.warning("Google translation failed: %s, trying fallback...", e)

    # 2. Fallback to MyMemory Translator
    if not translated_result:
        try:
            s = _lang_code_mymemory(source_lang)
            t = _lang_code_mymemory(target_lang)
            fallback_translator = MyMemoryTranslator(source=s, target=t, proxies=proxies)
            result = fallback_translator.translate(clean_text)
            if result and not str(result).startswith("MYMEMORY WARNING:"):
                translated_result = result
        except Exception as e:
            logger.error("MyMemory fallback translation failed: %s", e)

    if translated_result:
        # Cache translation for 30 days
        try:
            from services.redis_client import get_sync_redis
            sync_redis = get_sync_redis()
            if sync_redis is not None:
                sync_redis.set(cache_key, translated_result, ex=86400 * 30)
        except Exception:
            pass
        return translated_result

    return "❌ خطا در ترجمه! لطفاً کمی بعد دوباره تلاش کنید."
