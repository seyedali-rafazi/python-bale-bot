# services/telegram_public.py — parse public t.me embed HTML and forward media (≤20 MB)

import os
import re
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from bs4 import Tag
from telegram import Bot

from services.http_client import get_http_session

MAX_MEDIA_BYTES = 20 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CDN_URL_RE = re.compile(
    r"https://(?:cdn\d*\.telesco\.pe|[^/\s\"']+\.telegram-cdn\.org)/file/[^\s\"'<>]+"
)
PHOTO_BG_RE = re.compile(r"background-image:url\('([^']+)'\)")
SIZE_RE = re.compile(
    r"([\d.,]+)\s*(KB|MB|GB|K|M|G)\b", re.IGNORECASE
)


@dataclass
class MediaItem:
    kind: str  # photo, video, voice, audio, document
    url: str
    filename: str = "file"
    size_hint_bytes: Optional[int] = None


@dataclass
class ParsedMessage:
    text: str = ""
    items: list[MediaItem] = field(default_factory=list)


def _class_has(el: Tag, name: str) -> bool:
    classes = el.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return name in classes


def parse_size_hint(extra: str) -> Optional[int]:
    if not extra:
        return None
    m = SIZE_RE.search(extra.replace(",", "."))
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).upper()
    if unit in ("K", "KB"):
        return int(value * 1024)
    if unit in ("M", "MB"):
        return int(value * 1024 * 1024)
    if unit in ("G", "GB"):
        return int(value * 1024 * 1024 * 1024)
    return None


def _collect_cdn_urls(root: Tag) -> list[str]:
    found = []
    for attr in ("href", "src"):
        for el in root.find_all(attrs={attr: True}):
            val = el.get(attr, "")
            if "telesco.pe" in val or "telegram-cdn" in val:
                found.append(val)
    html = str(root)
    for m in CDN_URL_RE.finditer(html):
        found.append(m.group(0))
    # preserve order, dedupe
    seen = set()
    out = []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _photo_urls(msg: Tag) -> list[str]:
    urls = []
    for wrap in msg.find_all("a", class_="tgme_widget_message_photo_wrap"):
        style = wrap.get("style", "")
        m = PHOTO_BG_RE.search(style)
        if m:
            urls.append(m.group(1))
    return urls


def _video_urls(msg: Tag) -> list[str]:
    urls = []
    for el in msg.select(".tgme_widget_message_video"):
        src = el.get("src")
        if src and src not in urls:
            urls.append(src)
    for video in msg.find_all("video"):
        src = video.get("src")
        if src and src not in urls:
            urls.append(src)
        for source in video.find_all("source"):
            s = source.get("src")
            if s and s not in urls:
                urls.append(s)
    return urls


def _audio_items(msg: Tag) -> list[MediaItem]:
    items = []
    for audio in msg.find_all("audio"):
        src = audio.get("src")
        if not src:
            continue
        if _class_has(audio, "tgme_widget_message_voice"):
            items.append(MediaItem("voice", src, "voice.ogg"))
        else:
            items.append(MediaItem("audio", src, "audio.mp3"))
    return items


def _document_items(msg: Tag, pool: list[str]) -> list[MediaItem]:
    items = []
    used_urls: set[str] = set()

    for wrap in msg.find_all("a", class_="tgme_widget_message_document_wrap"):
        title_el = wrap.find(class_="tgme_widget_message_document_title")
        extra_el = wrap.find(class_="tgme_widget_message_document_extra")
        title = title_el.get_text(strip=True) if title_el else "document"
        extra = extra_el.get_text(strip=True) if extra_el else ""
        size_hint = parse_size_hint(extra)

        url = wrap.get("href", "")
        if not url.startswith("http") or "t.me/" in url:
            url = ""
        if not url:
            for a in wrap.find_all("a", href=True):
                h = a["href"]
                if ("telesco.pe" in h or "telegram-cdn" in h) and h not in used_urls:
                    url = h
                    break
        if not url:
            onclick = wrap.get("onclick", "") or ""
            m = re.search(r"https://[^\s'\"\\]+", onclick)
            if m:
                url = m.group(0)
        if not url:
            for au in wrap.find_all("audio", src=True):
                url = au["src"]
                break
        if not url and pool:
            for candidate in pool:
                if candidate not in used_urls:
                    url = candidate
                    break

        if url:
            used_urls.add(url)
            filename = title if "." in title else f"{title}.bin"
            kind = "audio" if url.endswith((".mp3", ".m4a", ".ogg")) else "document"
            items.append(
                MediaItem(kind, url, filename, size_hint_bytes=size_hint)
            )

    return items


def parse_message_element(msg: Tag) -> ParsedMessage:
    text_div = msg.find("div", class_="tgme_widget_message_text")
    text = text_div.get_text(separator="\n").strip() if text_div else ""

    cdn_pool = _collect_cdn_urls(msg)
    items: list[MediaItem] = []

    for url in _photo_urls(msg):
        items.append(MediaItem("photo", url, "photo.jpg"))

    for url in _video_urls(msg):
        items.append(MediaItem("video", url, "video.mp4"))

    items.extend(_audio_items(msg))

    doc_items = _document_items(msg, cdn_pool)
    items.extend(doc_items)

    used = {i.url for i in items}
    for url in cdn_pool:
        if url not in used:
            items.append(MediaItem("document", url, "file.bin"))
            used.add(url)

    return ParsedMessage(text=text, items=items)


def caption_for(text: str, use: bool) -> str:
    if not use or not text:
        return ""
    return text if len(text) <= 1024 else ""


async def _head_content_length(session, url: str) -> Optional[int]:
    try:
        async with session.head(
            url, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=15
        ) as resp:
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                return int(cl)
    except Exception:
        pass
    return None


async def download_media(
    url: str, filename: str, max_bytes: int = MAX_MEDIA_BYTES
) -> tuple[Optional[str], Optional[str]]:
    """Download to temp file. Returns (path, error_message)."""
    temp_path = f"temp_{uuid.uuid4().hex}_{filename}"
    session = await get_http_session()
    headers = {"User-Agent": USER_AGENT}

    content_length = await _head_content_length(session, url)
    if content_length is not None and content_length > max_bytes:
        return None, "over_20mb"

    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            if resp.status != 200:
                return None, f"http_{resp.status}"
            downloaded = 0
            with open(temp_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 512):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        f.close()
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        return None, "over_20mb"
                    f.write(chunk)
            if downloaded == 0:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None, "empty"
            return temp_path, None
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None, "download_failed"


async def _send_item(
    bot: Bot,
    chat_id: str,
    item: MediaItem,
    cap: str,
) -> tuple[bool, Optional[str]]:
    """Send one media item. Returns (sent, skip_reason)."""
    if item.size_hint_bytes is not None and item.size_hint_bytes > MAX_MEDIA_BYTES:
        return False, "over_20mb"

    if item.kind in ("photo", "video"):
        try:
            if item.kind == "photo":
                await bot.send_photo(
                    chat_id=chat_id, photo=item.url, caption=cap or None
                )
            else:
                await bot.send_video(
                    chat_id=chat_id, video=item.url, caption=cap or None
                )
            return True, None
        except Exception:
            pass

    temp_path = None
    try:
        temp_path, err = await download_media(item.url, item.filename)
        if err == "over_20mb":
            return False, "over_20mb"
        if not temp_path:
            return False, err or "send_failed"

        send_kwargs = dict(
            chat_id=chat_id,
            caption=cap or None,
            read_timeout=120,
            write_timeout=120,
        )
        if item.kind == "photo":
            with open(temp_path, "rb") as f:
                await bot.send_photo(photo=f, **send_kwargs)
        elif item.kind == "video":
            with open(temp_path, "rb") as f:
                await bot.send_video(video=f, **send_kwargs)
        elif item.kind == "voice":
            with open(temp_path, "rb") as f:
                await bot.send_voice(voice=f, **send_kwargs)
        elif item.kind == "audio":
            with open(temp_path, "rb") as f:
                await bot.send_audio(audio=f, **send_kwargs)
        else:
            with open(temp_path, "rb") as f:
                await bot.send_document(
                    document=f, filename=item.filename, **send_kwargs
                )
        return True, None
    except Exception:
        return False, "send_failed"
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


async def send_parsed_message(
    bot: Bot, chat_id: str, parsed: ParsedMessage
) -> bool:
    """Forward all media from a parsed public Telegram message."""
    sent_any = False
    skipped_large = 0
    cap = caption_for(parsed.text, True)

    for idx, item in enumerate(parsed.items):
        use_cap = cap if idx == 0 else ""
        ok, reason = await _send_item(bot, chat_id, item, use_cap)
        if ok:
            sent_any = True
            cap = ""
        elif reason == "over_20mb":
            skipped_large += 1

    if parsed.text and len(parsed.text) > 1024:
        await bot.send_message(chat_id=chat_id, text=parsed.text)
        sent_any = True
    elif parsed.text and not sent_any:
        await bot.send_message(chat_id=chat_id, text=parsed.text)
        sent_any = True

    if skipped_large:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ {skipped_large} فایل به‌دلیل حجم بالای ۲۰ مگابایت ارسال نشد."
            ),
        )

    return sent_any


def parse_html_message(soup, root=None) -> ParsedMessage:
    """Parse a single-message embed page (t.me/...?embed=1)."""
    if root is None:
        wrap = soup.find("div", class_="tgme_widget_message_wrap")
        if wrap:
            msg = wrap.find("div", class_="tgme_widget_message")
            if msg:
                return parse_message_element(msg)
        msg = soup.find("div", class_="tgme_widget_message")
        if msg:
            return parse_message_element(msg)
        return ParsedMessage()
    return parse_message_element(root)
