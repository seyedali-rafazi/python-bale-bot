# services/telegram_telethon.py — fetch public Telegram content via Telethon (MTProto)

import os
import re
import uuid
import asyncio
import logging
from typing import Optional

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    RPCError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
)

from telegram.error import RetryAfter

from core.state_manager import StateCache
from core.task_utils import bounded_large_upload, get_file_size_async, load_input_file
from services.ai import get_telethon_client
from services.telegram_public import MAX_MEDIA_BYTES

logger = logging.getLogger(__name__)

_TG_FETCH_CONCURRENCY = max(1, int(os.getenv("TG_FETCH_CONCURRENCY", "3")))
_tg_fetch_semaphore = asyncio.Semaphore(_TG_FETCH_CONCURRENCY)
_tg_download_semaphore = asyncio.Semaphore(_TG_FETCH_CONCURRENCY)
_channel_messages_cache = StateCache(max_capacity=150, default_ttl=90.0)
TG_DOWNLOAD_DIR = "tg_downloads"

_MESSAGE_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/([^/\s]+)/(\d+)",
    re.IGNORECASE,
)


def normalize_channel_id(text: str) -> str:
    raw = text.strip()
    for prefix in ("https://", "http://"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix) :]
    if raw.lower().startswith("t.me/"):
        raw = raw[5:]
    if raw.startswith("@"):
        raw = raw[1:]
    parts = [p for p in raw.split("/") if p and p.lower() not in ("s", "joinchat", "c")]
    return parts[0] if parts else raw


def parse_message_link(link: str) -> Optional[tuple[str, int]]:
    m = _MESSAGE_LINK_RE.search(link.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def _media_size(message) -> Optional[int]:
    if not message.media:
        return None
    if isinstance(message.media, MessageMediaPhoto):
        photo = getattr(message.media, "photo", None)
        sizes = getattr(photo, "sizes", None) or []
        byte_sizes = [getattr(s, "size", None) for s in sizes if getattr(s, "size", None)]
        return max(byte_sizes) if byte_sizes else getattr(photo, "size", None)
    if isinstance(message.media, MessageMediaDocument):
        return getattr(message.media.document, "size", None)
    return None


def _filename_from_document(document) -> str:
    for attr in document.attributes or []:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name
    mime = document.mime_type or ""
    if "pdf" in mime:
        return "file.pdf"
    if "zip" in mime:
        return "file.zip"
    if "video" in mime:
        return "video.mp4"
    if "audio" in mime:
        return "audio.mp3"
    return f"file_{document.id}"


async def _send_downloaded(
    bot,
    chat_id: str,
    path: str,
    message,
    caption: str,
) -> bool:
    from telethon.tl.types import MessageMediaDocument as DocMedia

    media = message.media
    cap = caption or None

    try:
        if isinstance(media, MessageMediaPhoto):
            async with bounded_large_upload():
                photo_file = await load_input_file(path, filename="photo.jpg")
                try:
                    try:
                        await bot.send_photo(chat_id=chat_id, photo=photo_file, caption=cap)
                    except RetryAfter as exc:
                        await asyncio.sleep(max(1.0, float(exc.retry_after)) + 0.5)
                        await bot.send_photo(chat_id=chat_id, photo=photo_file, caption=cap)
                finally:
                    del photo_file
            return True

        if isinstance(media, DocMedia):
            doc = media.document
            is_video = any(
                isinstance(a, DocumentAttributeVideo) for a in (doc.attributes or [])
            )
            is_voice = doc.mime_type == "audio/ogg"
            is_audio = any(
                isinstance(a, DocumentAttributeAudio) for a in (doc.attributes or [])
            )
            fname = _filename_from_document(doc)

            async def _send_doc_file(media_file):
                if is_video:
                    await bot.send_video(
                        chat_id=chat_id, video=media_file, caption=cap, filename=fname
                    )
                elif is_voice:
                    await bot.send_voice(chat_id=chat_id, voice=media_file, caption=cap)
                elif is_audio and not is_voice:
                    await bot.send_audio(
                        chat_id=chat_id, audio=media_file, caption=cap, filename=fname
                    )
                else:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=media_file,
                        filename=fname,
                        caption=cap,
                    )

            async with bounded_large_upload():
                media_file = await load_input_file(path, filename=fname)
                try:
                    try:
                        await _send_doc_file(media_file)
                    except RetryAfter as exc:
                        await asyncio.sleep(max(1.0, float(exc.retry_after)) + 0.5)
                        await _send_doc_file(media_file)
                finally:
                    del media_file
            return True
    except Exception as e:
        logger.warning("Bale send failed for telethon media: %s", e)
    return False


async def send_message_via_bot(bot, chat_id: str, message) -> bool:
    """Download one Telethon message (if media) and forward to Bale chat."""
    text = (message.message or message.text or "").strip()
    cap = text[:1024] if text else ""

    size = _media_size(message)
    if size is not None and size > MAX_MEDIA_BYTES:
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ این فایل ({size // (1024 * 1024)} مگابایت) بیش از ۵۰ مگابایت است.",
        )
        if len(text) > 1024:
            await bot.send_message(chat_id=chat_id, text=text)
        elif text and not message.media:
            await bot.send_message(chat_id=chat_id, text=text)
        return bool(text)

    if not message.media:
        if text:
            await bot.send_message(chat_id=chat_id, text=text)
            return True
        return False

    await asyncio.to_thread(os.makedirs, TG_DOWNLOAD_DIR, exist_ok=True)
    temp_path = None
    try:
        async with _tg_download_semaphore:
            client = await get_telethon_client()
            temp_path = await asyncio.wait_for(
                client.download_media(
                    message, file=os.path.join(TG_DOWNLOAD_DIR, f"tg_{uuid.uuid4().hex}")
                ),
                timeout=180.0,
            )
        if not temp_path or not await asyncio.to_thread(os.path.exists, temp_path):
            return False

        if await get_file_size_async(temp_path) > MAX_MEDIA_BYTES:
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ فایل پس از دانلود بیش از ۵۰ مگابایت بود و ارسال نشد.",
            )
            if len(text) > 1024:
                await bot.send_message(chat_id=chat_id, text=text)
            return bool(text)

        sent = await _send_downloaded(bot, chat_id, temp_path, message, cap)
        if sent and len(text) > 1024:
            await bot.send_message(chat_id=chat_id, text=text)
        return sent or bool(text and len(text) > 1024)
    except FloodWaitError as e:
        logger.warning("Telethon FloodWait during download_media: %ss", e.seconds)
        await bot.send_message(
            chat_id=chat_id,
            text=f"⛔ محدودیت موقت تلگرام. لطفاً {e.seconds} ثانیه بعد تلاش کنید.",
        )
        return False
    except Exception as e:
        logger.exception("telethon download/send failed: %s", e)
        if text:
            await bot.send_message(chat_id=chat_id, text=text)
            return True
        return False
    finally:
        if temp_path:
            def _cleanup_temp(p: str):
                if os.path.exists(p):
                    os.remove(p)
            try:
                await asyncio.to_thread(_cleanup_temp, temp_path)
            except OSError:
                pass


async def fetch_channel_messages(
    channel_id: str, limit: int = 20
) -> list:
    channel_id = normalize_channel_id(channel_id)
    if not channel_id:
        return []

    cache_key = f"{channel_id.lower()}:{limit}"
    cached = _channel_messages_cache.get(cache_key)
    if cached is not None:
        return cached

    async with _tg_fetch_semaphore:
        client = await get_telethon_client()
        logger.info("Telethon: resolving channel @%s", channel_id)
        entity = await asyncio.wait_for(client.get_entity(channel_id), timeout=30.0)
        messages = await asyncio.wait_for(client.get_messages(entity, limit=limit), timeout=30.0)
        result = list(messages or [])
        logger.info(
            "Telethon: got %s messages from @%s", len(result), channel_id
        )
        if result:
            _channel_messages_cache[cache_key] = result
        return result


async def fetch_single_message(link: str):
    parsed = parse_message_link(link)
    if not parsed:
        return None
    channel, msg_id = parsed
    async with _tg_fetch_semaphore:
        client = await get_telethon_client()
        logger.info("Telethon: fetch message %s/%s", channel, msg_id)
        entity = await asyncio.wait_for(client.get_entity(channel), timeout=30.0)
        messages = await asyncio.wait_for(client.get_messages(entity, ids=msg_id), timeout=30.0)
        if isinstance(messages, list):
            return messages[0] if messages else None
        return messages


async def telethon_available() -> bool:
    try:
        client = await get_telethon_client()
        return client.is_connected()
    except Exception as e:
        logger.warning("Telethon not available for Telegram downloads: %s", e)
        return False


def telethon_user_error(exc: Exception) -> str:
    if isinstance(exc, FloodWaitError):
        return f"⛔ محدودیت موقت تلگرام. لطفاً {exc.seconds} ثانیه بعد تلاش کنید."
    if isinstance(exc, (UsernameInvalidError, UsernameNotOccupiedError)):
        return "❌ آیدی کانال نامعتبر است."
    if isinstance(exc, ChannelPrivateError):
        return "❌ کانال خصوصی است یا ربات تلگرام به آن دسترسی ندارد."
    if isinstance(exc, RPCError):
        return f"❌ خطای تلگرام: {exc}"
    return "❌ خطا در دریافت از تلگرام (Telethon)."
