# services/ai.py

import os
import io
import urllib.parse
import asyncio
import logging
import aiohttp

from dotenv import load_dotenv
from gtts import gTTS
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

from services.http_client import get_http_session

load_dotenv()

logger = logging.getLogger(__name__)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
CHATGPT_BOT_USERNAME = os.getenv("CHATGPT_BOT_USERNAME")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("AI_SESSION_NAME", "SESSION_NAME")

# -----------------------------
# Telethon client (singleton)
# -----------------------------
_ai_client: TelegramClient | None = None
_ai_client_lock = asyncio.Lock()
_ai_chat_lock = asyncio.Lock()
_ai_connected = False


def _build_ai_client() -> TelegramClient:
    return TelegramClient(
        SESSION_NAME,
        API_ID,
        API_HASH,
    )


async def init_ai_client():
    """
    ساخت و اتصال یک‌باره Telethon client
    """
    global _ai_client, _ai_connected

    async with _ai_client_lock:
        if _ai_client is None:
            _ai_client = _build_ai_client()

        if not _ai_connected:
            await _ai_client.connect()

            if not await _ai_client.is_user_authorized():
                raise Exception("Telethon account is not authorized")

            _ai_connected = True
            logger.info("✅ Telethon AI client connected")


async def close_ai_client():
    global _ai_client, _ai_connected

    async with _ai_client_lock:
        if _ai_client is not None:
            try:
                await _ai_client.disconnect()
            except Exception as e:
                logger.error(f"close_ai_client error: {e}")
            finally:
                _ai_connected = False


async def _ensure_ai_client() -> TelegramClient:
    await init_ai_client()

    if _ai_client is None:
        raise RuntimeError("AI client is not initialized")

    if not _ai_client.is_connected():
        async with _ai_client_lock:
            if not _ai_client.is_connected():
                await _ai_client.connect()

    return _ai_client


async def ask_chatbot(text: str) -> str:
    """
    ارسال پیام به ربات تلگرامی AI از طریق Telethon

    نکته مهم:
    چون همه درخواست‌ها داخل یک دیالوگ واحد با یک بات مقصد هستند،
    برای جلوگیری از قاطی شدن پاسخ‌ها این بخش عمداً با lock تک‌به‌تک شده.
    این lock فقط بخش chat را serialize می‌کند، نه کل ربات را.
    OCR/TTS/Image همچنان همزمان کار می‌کنند.
    """
    async with _ai_chat_lock:
        try:
            client = await _ensure_ai_client()

            prompt = (
                "این یک درخواست کاملاً مستقل است. "
                "به هیچ عنوان از پیام‌های قبلی به عنوان کانتکست استفاده نکن.\n"
                "نام کاربر را در پاسخ نیاور، سلام و احوال‌پرسی نکن و مستقیم فقط پاسخ بده:\n"
                f"{text}"
            )

            # قبل از ارسال، آخرین پیام ورودی را یادداشت می‌کنیم
            before_messages = await client.get_messages(CHATGPT_BOT_USERNAME, limit=1)
            before_id = before_messages[0].id if before_messages else 0

            await asyncio.wait_for(
                client.send_message(CHATGPT_BOT_USERNAME, prompt),
                timeout=15,
            )

            last_text = ""
            stable_count = 0

            for _ in range(40):
                await asyncio.sleep(2)

                messages = await client.get_messages(CHATGPT_BOT_USERNAME, limit=5)
                if not messages:
                    continue

                candidate = None

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

                    candidate = current_text
                    break

                if not candidate:
                    continue

                if candidate == last_text:
                    stable_count += 1
                else:
                    last_text = candidate
                    stable_count = 0

                if stable_count >= 1:
                    return candidate

            return "❌ زمان انتظار پایان یافت و ربات مقصد پاسخ کامل نداد."

        except asyncio.TimeoutError:
            return "⏳ پاسخ‌گویی سرور AI بیش از حد طول کشید."

        except FloodWaitError as e:
            return f"⛔ محدودیت تلگرام. لطفاً {e.seconds} ثانیه بعد دوباره تلاش کنید."

        except RPCError as e:
            logger.error(f"Telethon RPC error: {e}")
            return "❌ خطا در ارتباط با تلگرام."

        except Exception as e:
            logger.exception(f"ask_chatbot error: {e}")
            return "❌ خطا در برقراری ارتباط با ربات هوش مصنوعی."


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
            return "❌ خطا در پردازش تصویر توسط سرور OCR."

        parsed_results = result.get("ParsedResults")
        if parsed_results and len(parsed_results) > 0:
            text = parsed_results[0].get("ParsedText", "متنی یافت نشد.")
            return text if text.strip() else "❌ متنی در این تصویر تشخیص داده نشد."

        return "❌ ساختار پاسخ سرور OCR نامعتبر بود."

    except asyncio.TimeoutError:
        return "❌ سرور OCR دیر پاسخ داد. لطفاً بعداً دوباره تلاش کنید."
    except Exception as e:
        logger.exception(f"perform_ocr error: {e}")
        return "❌ خطا در ارتباط با سرور OCR."


def _sync_tts(text: str):
    lang = "fa" if any("\u0600" <= c <= "\u06ff" for c in text) else "en"
    tts = gTTS(text=text, lang=lang, slow=False)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp


async def text_to_speech(text: str):
    try:
        return await asyncio.to_thread(_sync_tts, text)
    except Exception as e:
        logger.exception(f"text_to_speech error: {e}")
        return None


async def generate_image(prompt: str):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1024&height=1024&nologo=true"
        )

        timeout = aiohttp.ClientTimeout(total=30)
        session = await get_http_session()

        async with session.get(url, timeout=timeout) as response:
            if response.status == 200:
                image_bytes = await response.read()
                fp = io.BytesIO(image_bytes)
                fp.seek(0)
                return fp

        return None

    except asyncio.TimeoutError:
        logger.error("generate_image timeout")
        return None
    except Exception as e:
        logger.exception(f"generate_image error: {e}")
        return None
