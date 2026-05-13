# services/ai.py


import os
import io
import uuid
import asyncio
import logging
import urllib.parse
import aiohttp

from dotenv import load_dotenv
from gtts import gTTS

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RPCError

from services.http_client import get_http_session

load_dotenv()

logger = logging.getLogger(__name__)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
CHATGPT_BOT_USERNAME = os.getenv("CHATGPT_BOT_USERNAME")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("AI_SESSION_NAME", "ai_session")

# =========================================================
# TELETHON
# =========================================================

_ai_client: TelegramClient | None = None
_ai_client_lock = asyncio.Lock()
_ai_connected = False

# request_id -> Future
_pending_ai_requests: dict[str, asyncio.Future] = {}

# جلوگیری از اسپم بیش از حد
_ai_send_semaphore = asyncio.Semaphore(5)


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

            _register_ai_handlers(_ai_client)

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


# =========================================================
# EVENT BASED RESPONSE HANDLER
# =========================================================


def _register_ai_handlers(client: TelegramClient):

    @client.on(events.NewMessage(from_users=CHATGPT_BOT_USERNAME))
    async def ai_message_handler(event):

        try:
            text = event.raw_text

            if not text:
                return

            lines = text.splitlines()

            if not lines:
                return

            first_line = lines[0].strip()

            if not first_line.startswith("[REQ_ID:"):
                return

            request_id = first_line.replace("[REQ_ID:", "").replace("]", "").strip()

            future = _pending_ai_requests.get(request_id)

            if not future:
                return

            answer = "\n".join(lines[1:]).strip()

            if not answer:
                answer = "❌ پاسخ خالی دریافت شد."

            if not future.done():
                future.set_result(answer)

            _pending_ai_requests.pop(request_id, None)

        except Exception:
            logger.exception("ai_message_handler failed")


# =========================================================
# CHAT BOT
# =========================================================


async def ask_chatbot(text: str) -> str:

    request_id = str(uuid.uuid4())[:8]

    loop = asyncio.get_running_loop()

    future = loop.create_future()

    _pending_ai_requests[request_id] = future

    try:
        client = await _ensure_ai_client()

        prompt = (
            f"[REQ_ID:{request_id}]\n\n"
            "این درخواست کاملاً مستقل است.\n"
            "از پیام‌های قبلی استفاده نکن.\n"
            "بدون سلام و احوالپرسی پاسخ بده.\n\n"
            f"{text}"
        )

        async with _ai_send_semaphore:
            await asyncio.wait_for(
                client.send_message(
                    CHATGPT_BOT_USERNAME,
                    prompt,
                ),
                timeout=15,
            )

        answer = await asyncio.wait_for(
            future,
            timeout=90,
        )

        return answer

    except asyncio.TimeoutError:
        _pending_ai_requests.pop(request_id, None)

        return "⏳ زمان پاسخ AI به پایان رسید."

    except FloodWaitError as e:
        _pending_ai_requests.pop(request_id, None)

        return f"⛔ محدودیت تلگرام.\n{e.seconds} ثانیه بعد دوباره تلاش کنید."

    except RPCError:
        logger.exception("Telethon RPC Error")

        _pending_ai_requests.pop(request_id, None)

        return "❌ خطا در ارتباط با تلگرام."

    except Exception:
        logger.exception("ask_chatbot failed")

        _pending_ai_requests.pop(request_id, None)

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
# IMAGE GENERATION
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
