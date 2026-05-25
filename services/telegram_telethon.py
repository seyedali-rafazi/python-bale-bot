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

from services.ai import get_telethon_client
from services.telegram_public import MAX_MEDIA_BYTES

logger = logging.getLogger(__name__)

_tg_fetch_lock = asyncio.Lock()
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
        return getattr(message.media.photo, "size", None)
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
            with open(path, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=cap)
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

            with open(path, "rb") as f:
                if is_video:
                    await bot.send_video(
                        chat_id=chat_id, video=f, caption=cap, filename=fname
                    )
                elif is_voice:
                    await bot.send_voice(chat_id=chat_id, voice=f, caption=cap)
                elif is_audio and not is_voice:
                    await bot.send_audio(
                        chat_id=chat_id, audio=f, caption=cap, filename=fname
                    )
                else:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=fname,
                        caption=cap,
                    )
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
            text=f"⚠️ این فایل ({size // (1024 * 1024)} مگابایت) بیش از ۲۰ مگابایت است.",
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

    os.makedirs(TG_DOWNLOAD_DIR, exist_ok=True)
    temp_path = None
    try:
        async with _tg_fetch_lock:
            client = await get_telethon_client()
            temp_path = await client.download_media(
                message, file=os.path.join(TG_DOWNLOAD_DIR, f"tg_{uuid.uuid4().hex}")
            )
        if not temp_path or not os.path.exists(temp_path):
            return False

        if os.path.getsize(temp_path) > MAX_MEDIA_BYTES:
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ فایل پس از دانلود بیش از ۲۰ مگابایت بود و ارسال نشد.",
            )
            if len(text) > 1024:
                await bot.send_message(chat_id=chat_id, text=text)
            return bool(text)

        sent = await _send_downloaded(bot, chat_id, temp_path, message, cap)
        if sent and len(text) > 1024:
            await bot.send_message(chat_id=chat_id, text=text)
        return sent or bool(text and len(text) > 1024)
    except Exception as e:
        logger.exception("telethon download/send failed: %s", e)
        if text:
            await bot.send_message(chat_id=chat_id, text=text)
            return True
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


async def fetch_channel_messages(
    channel_id: str, limit: int = 20
) -> list:
    channel_id = normalize_channel_id(channel_id)
    if not channel_id:
        return []

    async with _tg_fetch_lock:
        client = await get_telethon_client()
        logger.info("Telethon: resolving channel @%s", channel_id)
        entity = await client.get_entity(channel_id)
        messages = await client.get_messages(entity, limit=limit)
        logger.info(
            "Telethon: got %s messages from @%s", len(messages or []), channel_id
        )
        return list(messages or [])


async def fetch_single_message(link: str):
    parsed = parse_message_link(link)
    if not parsed:
        return None
    channel, msg_id = parsed
    async with _tg_fetch_lock:
        client = await get_telethon_client()
        logger.info("Telethon: fetch message %s/%s", channel, msg_id)
        entity = await client.get_entity(channel)
        messages = await client.get_messages(entity, ids=msg_id)
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
    if isinstance(exc, (UsernameInvalidError, UsernameNotOccupiedError)):
        return "❌ آیدی کانال نامعتبر است."
    if isinstance(exc, ChannelPrivateError):
        return "❌ کانال خصوصی است یا ربات تلگرام به آن دسترسی ندارد."
    if isinstance(exc, RPCError):
        return f"❌ خطای تلگرام: {exc}"
    return "❌ خطا در دریافت از تلگرام (Telethon)."
