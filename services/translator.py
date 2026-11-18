# services/translator.py

import asyncio
import hashlib
import json
import os
import logging
import threading
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
_cached_mymemory: dict[tuple[str, str], object] = {}
_translator_lock = threading.Lock()
_TRANSLATE_SEMAPHORE = asyncio.Semaphore(max(2, int(os.getenv("TRANSLATE_MAX_CONCURRENT", "8"))))
_inflight_translations: dict[str, asyncio.Task] = {}


def _lang_code_mymemory(lang: str) -> str:
    return _MYMEMORY_LANG_MAP.get(lang.lower(), lang)


def _translation_cache_key(source_lang: str, target_lang: str, clean_text: str) -> str:
    text_hash = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
    return f"tr:{source_lang}:{target_lang}:{text_hash}"


def _translate_sync_no_cache(source_lang: str, target_lang: str, clean_text: str) -> str | None:
    """Execute blocking translation providers without redundant sync Redis I/O."""
    translated_result = None

    # 1. Try Google Translator
    try:
        with _translator_lock:
            translator = cached_translators.get((source_lang, target_lang))
            if not translator:
                translator = GoogleTranslator(
                    source=source_lang, target=target_lang, proxies=proxies
                )
                cached_translators[(source_lang, target_lang)] = translator
        result = translator.translate(clean_text)
        if result and not str(result).startswith("Server Error:"):
            translated_result = result
        else:
            logger.warning("Google translator returned server error or empty result, trying fallback...")
    except Exception as e:
        logger.warning("Google translation failed: %s, trying fallback...", e)

    # 2. Fallback to MyMemory Translator
    if not translated_result and MyMemoryTranslator is not None:
        try:
            s = _lang_code_mymemory(source_lang)
            t = _lang_code_mymemory(target_lang)
            with _translator_lock:
                fallback_translator = _cached_mymemory.get((s, t))
                if not fallback_translator:
                    fallback_translator = MyMemoryTranslator(source=s, target=t, proxies=proxies)
                    _cached_mymemory[(s, t)] = fallback_translator
            result = fallback_translator.translate(clean_text)
            if result and not str(result).startswith("MYMEMORY WARNING:"):
                translated_result = result
        except Exception as e:
            logger.error("MyMemory fallback translation failed: %s", e)

    return translated_result


def translate_text(source_lang: str, target_lang: str, text: str) -> str:
    if not text or not text.strip():
        return "❌ لطفاً متنی برای ترجمه وارد کنید."

    clean_text = text.strip()
    cache_key = f"bale:cache:{_translation_cache_key(source_lang, target_lang, clean_text)}"
    sync_redis = None
    try:
        from services.redis_client import get_sync_redis
        sync_redis = get_sync_redis()
        if sync_redis is not None:
            cached_val = sync_redis.get(cache_key)
            if cached_val:
                try:
                    decoded = json.loads(cached_val)
                    if isinstance(decoded, str) and decoded:
                        return decoded
                except Exception:
                    return cached_val
    except Exception:
        pass

    translated_result = _translate_sync_no_cache(source_lang, target_lang, clean_text)

    if translated_result:
        # Cache translation for 30 days using the same JSON format as cache_service
        if sync_redis is not None:
            try:
                sync_redis.set(cache_key, json.dumps(translated_result, ensure_ascii=False), ex=86400 * 30)
            except Exception:
                pass
        return translated_result

    return "❌ خطا در ترجمه! لطفاً کمی بعد دوباره تلاش کنید."


_ORIG_TRANSLATE_TEXT = translate_text


async def async_translate_text(source_lang: str, target_lang: str, text: str) -> str:
    """Async translation: checks async Redis/local cache first without consuming a thread or double-hitting Redis."""
    if not text or not text.strip():
        return "❌ لطفاً متنی برای ترجمه وارد کنید."

    clean_text = text.strip()
    from services.cache_service import cache_get, cache_set

    sub_key = _translation_cache_key(source_lang, target_lang, clean_text)
    cached = await cache_get(sub_key)
    if isinstance(cached, str) and cached:
        return cached

    existing = _inflight_translations.get(sub_key)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    async def _do_translate() -> str:
        async with _TRANSLATE_SEMAPHORE:
            if translate_text is not _ORIG_TRANSLATE_TEXT:
                result = await asyncio.to_thread(
                    translate_text, source_lang, target_lang, clean_text
                )
            else:
                translated = await asyncio.to_thread(
                    _translate_sync_no_cache, source_lang, target_lang, clean_text
                )
                result = translated or "❌ خطا در ترجمه! لطفاً کمی بعد دوباره تلاش کنید."

        if result and not result.startswith("❌"):
            await cache_set(sub_key, result, ttl_sec=86400 * 30)
        return result

    task = asyncio.create_task(_do_translate())
    _inflight_translations[sub_key] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _inflight_translations.get(sub_key) is done_task:
            _inflight_translations.pop(sub_key, None)
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)
