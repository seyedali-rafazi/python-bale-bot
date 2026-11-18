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
from telethon.errors import FloodWaitError, RPCError

from services.http_client import get_http_session

load_dotenv()

logger = logging.getLogger(__name__)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
CHATGPT_BOT_USERNAME = os.getenv("CHATGPT_BOT_USERNAME" , "@UnlimitChatGPTbot")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("AI_SESSION_NAME", "ai_session")
AI_RESPONSE_TIMEOUT_SEC = max(10.0, float(os.getenv("AI_RESPONSE_TIMEOUT_SEC", "28")))

# =========================================================
# TELETHON
# =========================================================

_ai_client: TelegramClient | None = None

_ai_client_lock = asyncio.Lock()

# مهم‌ترین بخش
# فقط AI interaction serialize میشه
_ai_chat_lock = asyncio.Lock()
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
# AI CHAT
# =========================================================


async def ask_chatbot(text: str) -> str:
    # Serialize messages to the single Telegram bot chat so replies never mix across users
    async with _ai_chat_lock:
        try:
            client = await _ensure_ai_client()

            prompt = (
                "این درخواست کاملاً مستقل است.\n"
                "از پیام‌های قبلی استفاده نکن.\n"
                "بدون سلام و احوالپرسی پاسخ بده.\n\n"
                f"{text}"
            )

            sent_msg = None
            try:
                async with client.conversation(
                    CHATGPT_BOT_USERNAME,
                    timeout=AI_RESPONSE_TIMEOUT_SEC,
                    total_timeout=AI_RESPONSE_TIMEOUT_SEC,
                    exclusive=False,
                ) as conv:
                    sent_msg = await asyncio.wait_for(
                        conv.send_message(prompt),
                        timeout=15,
                    )

                    while True:
                        msg = await conv.get_response()
                        if getattr(msg, "sticker", None):
                            continue
                        if not msg.text:
                            continue
                        current_text = msg.text.strip()
                        if len(current_text) < 5:
                            continue
                        return current_text

            except asyncio.TimeoutError:
                # Single fallback check in case update delivery lagged behind RPC
                if sent_msg is not None:
                    messages = await asyncio.wait_for(
                        client.get_messages(
                            CHATGPT_BOT_USERNAME,
                            limit=5,
                        ),
                        timeout=10.0,
                    )
                    for msg in messages or []:
                        if msg.id <= sent_msg.id or msg.out:
                            continue
                        if getattr(msg, "sticker", None) or not msg.text:
                            continue
                        current_text = msg.text.strip()
                        if len(current_text) >= 5:
                            return current_text
                return "⏳ زمان پاسخ AI تمام شد."

        except FloodWaitError as e:
            return f"⛔ محدودیت تلگرام.\n{e.seconds} ثانیه بعد تلاش کنید."

        except RPCError:
            logger.exception("Telethon RPC Error")
            return "❌ خطا در ارتباط با تلگرام."

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
