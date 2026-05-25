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

# =========================================================
# TELETHON
# =========================================================

_ai_client: TelegramClient | None = None

_ai_client_lock = asyncio.Lock()

# مهم‌ترین بخش
# فقط AI interaction serialize میشه
_ai_chat_lock = asyncio.Lock()

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
            await _ai_client.connect()

            if not await _ai_client.is_user_authorized():
                raise Exception("Telethon account is not authorized")

            _ai_connected = True

            logger.info("✅ AI Telethon connected")


async def close_ai_client():

    global _ai_connected

    async with _ai_client_lock:
        if _ai_client:
            try:
                await _ai_client.disconnect()

            except Exception:
                logger.exception("close_ai_client failed")

        _ai_connected = False


async def _ensure_ai_client() -> TelegramClient:

    await init_ai_client()

    if _ai_client is None:
        raise RuntimeError("AI client not initialized")

    if not _ai_client.is_connected():
        async with _ai_client_lock:
            if not _ai_client.is_connected():
                await _ai_client.connect()

    return _ai_client


async def get_telethon_client() -> TelegramClient:
    """Shared Telethon session (AI + Telegram channel/message downloads)."""
    return await _ensure_ai_client()


# =========================================================
# AI CHAT
# =========================================================


async def ask_chatbot(text: str) -> str:
    # فقط این قسمت queue میشه
    async with _ai_chat_lock:
        try:
            client = await _ensure_ai_client()

            prompt = (
                "این درخواست کاملاً مستقل است.\n"
                "از پیام‌های قبلی استفاده نکن.\n"
                "بدون سلام و احوالپرسی پاسخ بده.\n\n"
                f"{text}"
            )

            # آخرین پیام قبل از ارسال
            before_messages = await client.get_messages(
                CHATGPT_BOT_USERNAME,
                limit=1,
            )

            before_id = before_messages[0].id if before_messages else 0

            # ارسال پیام
            await asyncio.wait_for(
                client.send_message(
                    CHATGPT_BOT_USERNAME,
                    prompt,
                ),
                timeout=15,
            )

            # انتظار پاسخ (بدون نیاز به stable_count برای ربات جدید)
            for _ in range(45):
                await asyncio.sleep(1.5)  # زمان خواب را هم کمی کمتر کردیم

                messages = await client.get_messages(
                    CHATGPT_BOT_USERNAME,
                    limit=5,
                )

                if not messages:
                    continue

                for msg in messages:
                    if msg.id <= before_id:
                        continue

                    if msg.out:
                        continue

                    if getattr(msg, "sticker", None):
                        continue

                    if not msg.text:
                        continue

                    current_text = msg.text.strip()

                    if len(current_text) < 5:
                        continue

                    # به محض پیدا کردن پاسخ از ربات جدید، آن را برمی‌گرداند
                    return current_text

            return "❌ AI پاسخ کامل نداد."

        except asyncio.TimeoutError:
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

        async with session.get(
            url,
            timeout=timeout,
        ) as response:
            if response.status != 200:
                return None

            image_bytes = await response.read()

        fp = io.BytesIO(image_bytes)

        fp.seek(0)

        return fp

    except asyncio.TimeoutError:
        logger.error("generate_image timeout")

        return None

    except Exception:
        logger.exception("generate_image failed")

        return None
