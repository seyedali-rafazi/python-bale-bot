# services/ai.py

import os
import io
import asyncio
import logging
import urllib.parse
import aiohttp

from dotenv import load_dotenv
from gtts import gTTS

from telethon import TelegramClient

from services.http_client import get_http_session

load_dotenv()

logger = logging.getLogger(__name__)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
GROQ_API_KEY = (os.getenv("groq_api") or os.getenv("GROQ_API_KEY") or "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("AI_SESSION_NAME", "ai_session")
AI_RESPONSE_TIMEOUT_SEC = max(10.0, float(os.getenv("AI_RESPONSE_TIMEOUT_SEC", "28")))

# =========================================================
# TELETHON (shared session for Telegram downloads)
# =========================================================

_ai_client: TelegramClient | None = None

_ai_client_lock = asyncio.Lock()

_TTS_SEMAPHORE = asyncio.Semaphore(max(2, int(os.getenv("TTS_MAX_CONCURRENT", "4"))))
_IMAGE_GEN_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("IMAGE_GEN_MAX_CONCURRENT", "3"))))

_ai_connected = False


def _build_ai_client() -> TelegramClient:

    return TelegramClient(
        SESSION_NAME,
        API_ID,
        API_HASH,
    )


async def init_ai_client():

    global _ai_client, _ai_connected

    async with _ai_client_lock:
        if _ai_client is None:
            _ai_client = _build_ai_client()

        if not _ai_connected:
            await asyncio.wait_for(_ai_client.connect(), timeout=20.0)

            if not await asyncio.wait_for(_ai_client.is_user_authorized(), timeout=15.0):
                raise Exception("Telethon account is not authorized")

            _ai_connected = True

            logger.info("✅ AI Telethon connected")


async def close_ai_client():

    global _ai_client, _ai_connected

    async with _ai_client_lock:
        if _ai_client:
            try:
                await asyncio.wait_for(_ai_client.disconnect(), timeout=10.0)

            except Exception:
                logger.exception("close_ai_client failed")

        _ai_client = None
        _ai_connected = False


async def _ensure_ai_client() -> TelegramClient:
    global _ai_connected

    if _ai_client is not None and _ai_connected and _ai_client.is_connected():
        return _ai_client

    await init_ai_client()

    if _ai_client is None:
        raise RuntimeError("AI client not initialized")

    if not _ai_client.is_connected():
        async with _ai_client_lock:
            if not _ai_client.is_connected():
                await asyncio.wait_for(_ai_client.connect(), timeout=20.0)
                if not await asyncio.wait_for(_ai_client.is_user_authorized(), timeout=15.0):
                    _ai_connected = False
                    raise RuntimeError("Telethon account is not authorized")
                _ai_connected = True

    return _ai_client


async def get_telethon_client() -> TelegramClient:
    """Shared Telethon session (AI + Telegram channel/message downloads)."""
    return await _ensure_ai_client()


# =========================================================
# AI CHAT (GROQ)
# =========================================================


async def ask_chatbot(text: str) -> str:
    api_key = (GROQ_API_KEY or os.getenv("groq_api") or os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        logger.error("Groq API key (groq_api / GROQ_API_KEY) is not configured")
        return "❌ کلید API هوش مصنوعی تنظیم نشده است."

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful AI assistant. Respond directly and clearly "
                    "in the same language as the user (e.g., Persian if the user writes in Persian), "
                    "without unnecessary greetings."
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        session = await get_http_session()
        async with session.post(
            GROQ_API_URL,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=AI_RESPONSE_TIMEOUT_SEC),
        ) as resp:
            if resp.status == 429:
                return "⛔ محدودیت درخواست Groq. لطفاً چند لحظه بعد دوباره تلاش کنید."
            if resp.status != 200:
                err_body = await resp.text()
                logger.warning("Groq API returned status %s: %s", resp.status, err_body[:300])
                return "❌ خطا در ارتباط با AI."

            data = await resp.json()
            choices = data.get("choices") or []
            if choices:
                content = (choices[0].get("message") or {}).get("content") or ""
                content = content.strip()
                if content:
                    return content
            return "❌ پاسخی از هوش مصنوعی دریافت نشد."

    except asyncio.TimeoutError:
        return "⏳ زمان پاسخ AI تمام شد."

    except Exception:
        logger.exception("ask_chatbot failed")
        return "❌ خطا در ارتباط با AI."


# =========================================================
# OCR
# =========================================================


async def perform_ocr(image_bytes: bytes) -> str:

    try:
        data = aiohttp.FormData()

        data.add_field("apikey", OCR_SPACE_API_KEY)

        data.add_field("language", "ara")

        data.add_field(
            "filename",
            image_bytes,
            filename="image.jpg",
            content_type="image/jpeg",
        )

        timeout = aiohttp.ClientTimeout(total=25)

        session = await get_http_session()

        async with session.post(
            "https://api.ocr.space/parse/image",
            data=data,
            timeout=timeout,
        ) as response:
            if response.status != 200:
                logger.warning("OCR HTTP status %s", response.status)
                return "❌ خطا در سرویس OCR."
            result = await response.json()

        if result.get("IsErroredOnProcessing"):
            return "❌ خطا در OCR."

        parsed_results = result.get("ParsedResults")

        if parsed_results and len(parsed_results) > 0:
            text = parsed_results[0].get("ParsedText", "")

            if text.strip():
                return text

            return "❌ متنی پیدا نشد."

        return "❌ پاسخ OCR نامعتبر بود."

    except asyncio.TimeoutError:
        return "❌ سرور OCR دیر پاسخ داد."

    except Exception:
        logger.exception("perform_ocr failed")

        return "❌ خطا در OCR."


# =========================================================
# TTS
# =========================================================


def _sync_tts(text: str):

    lang = "fa" if any("\u0600" <= c <= "\u06ff" for c in text) else "en"

    tts = gTTS(
        text=text,
        lang=lang,
        slow=False,
    )

    fp = io.BytesIO()

    tts.write_to_fp(fp)

    fp.seek(0)

    return fp


async def text_to_speech(text: str):

    try:
        async with _TTS_SEMAPHORE:
            return await asyncio.to_thread(
                _sync_tts,
                text,
            )

    except Exception:
        logger.exception("text_to_speech failed")

        return None


# =========================================================
# IMAGE
# =========================================================


async def generate_image(prompt: str):

    try:
        encoded_prompt = urllib.parse.quote(prompt)

        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1024&height=1024&nologo=true"
        )

        timeout = aiohttp.ClientTimeout(total=40)

        session = await get_http_session()

        async with _IMAGE_GEN_SEMAPHORE:
            async with session.get(
                url,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    return None

                max_image_bytes = 25 * 1024 * 1024
                cl = response.headers.get("Content-Length")
                if cl and cl.isdigit() and int(cl) > max_image_bytes:
                    logger.warning("generate_image response too large: %s bytes", cl)
                    return None

                fp = io.BytesIO()
                total_len = 0
                async for chunk in response.content.iter_chunked(65536):
                    total_len += len(chunk)
                    if total_len > max_image_bytes:
                        logger.warning("generate_image stream exceeded %s bytes", max_image_bytes)
                        fp.close()
                        return None
                    fp.write(chunk)

        fp.seek(0)

        return fp

    except asyncio.TimeoutError:
        logger.error("generate_image timeout")

        return None

    except Exception:
        logger.exception("generate_image failed")

        return None
