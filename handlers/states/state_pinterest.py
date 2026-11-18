# handlers/states/state_pinterest.py

import asyncio
import re
from io import BytesIO
from typing import List, Optional

import aiohttp
from services.http_client import get_http_session

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from core.state_manager import StateCache, clear_state, set_state
from core.task_utils import track_task
from handlers.utils import safe_answer_query

from core.database import (
    get_pinterest_downloads,
    increment_pinterest_downloads,
    is_vip,
)
from services.rate_limiter import user_action_lock

from core.limits import get_limit

from services.pinterest_queue import (
    PinterestQueueFullError,
    estimate_pinterest_wait_seconds,
    pinterest_search_timeout_seconds,
    queued_pinterest_search,
)

# =========================
# تنظیمات Performance
# =========================

# هم‌زمانی بالا باعث 429/بلاک از i.pinimg.com و خالی شدن نتایج می‌شود
DOWNLOAD_CONCURRENCY = 6

SEND_BATCH_SIZE = 10
MAX_PIN_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB per image safety cap
MIN_PIN_IMAGE_BYTES = 5 * 1024  # 5 KB floor to skip tiny UI icons/placeholders
_PIN_SIZE_SEGMENT_RE = re.compile(r"/(originals|1200x|736x|564x|474x|236x)/", re.IGNORECASE)

download_semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
_pin_pagination_cache = StateCache(max_capacity=3000, default_ttl=3600.0)

# =========================


def build_more_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ عکس‌های بیشتر",
                    callback_data="more_pins",
                )
            ]
        ]
    )


def _build_pin_fallback_urls(url: str) -> List[str]:
    """Generate ordered HD fallback URLs (originals -> 736x -> 564x -> 474x) for i.pinimg.com."""
    candidates = [url]
    if "i.pinimg.com" in url.lower() and _PIN_SIZE_SEGMENT_RE.search(url):
        for size in ("736x", "564x", "474x"):
            alt = _PIN_SIZE_SEGMENT_RE.sub(f"/{size}/", url, count=1)
            if alt not in candidates:
                candidates.append(alt)
    return candidates


async def get_image_bytes(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
) -> Optional[BytesIO]:

    candidate_urls = _build_pin_fallback_urls(url)

    async with download_semaphore:
        for candidate_url in candidate_urls:
            for attempt in range(2):
                try:
                    async with session.get(
                        candidate_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=25),
                        allow_redirects=True,
                    ) as res:
                        if res.status in (403, 404, 410):
                            # Size variant (e.g. /originals/.jpg) missing; try next HD fallback
                            break
                        if res.status in (429, 503) and attempt == 0:
                            await asyncio.sleep(0.5)
                            continue
                        if res.status != 200:
                            if attempt == 0:
                                await asyncio.sleep(0.3)
                                continue
                            break

                        content_type = res.headers.get("Content-Type", "").lower()
                        if "image" not in content_type:
                            break

                        content_length = res.headers.get("Content-Length")
                        if content_length and content_length.isdigit():
                            cl = int(content_length)
                            if cl > MAX_PIN_IMAGE_BYTES or cl < MIN_PIN_IMAGE_BYTES:
                                break

                        bio = BytesIO()
                        total_bytes = 0

                        async for chunk in res.content.iter_chunked(65536):
                            total_bytes += len(chunk)
                            if total_bytes > MAX_PIN_IMAGE_BYTES:
                                bio.close()
                                bio = None
                                break
                            bio.write(chunk)

                        if bio is None:
                            break
                        if total_bytes < MIN_PIN_IMAGE_BYTES:
                            bio.close()
                            break

                        bio.seek(0)
                        bio.name = "pinterest.jpg"
                        return bio

                except Exception as e:
                    print(f"download image error (try {attempt + 1}): {e}")
                    if attempt == 0:
                        await asyncio.sleep(0.4)
                        continue
                    break
        return None


async def send_image_batch(
    chat_id: str,
    context: ContextTypes.DEFAULT_TYPE,
    urls: List[str],
) -> int:
    """Download and send up to 10 images with a bounded 3-slot queue so RAM stays minimal."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0.0.0 "
            "Safari/537.36"
        ),
        "Referer": "https://www.pinterest.com/",
    }

    target_urls = list(urls[:10])
    if not target_urls:
        return 0

    session = await get_http_session()
    buffer_queue: asyncio.Queue[Optional[BytesIO]] = asyncio.Queue(maxsize=3)
    url_iter = iter(target_urls)
    worker_count = min(3, len(target_urls))

    async def _worker() -> None:
        while True:
            try:
                url = next(url_iter)
            except StopIteration:
                break
            img = None
            try:
                img = await get_image_bytes(session, url, headers=headers)
            except Exception as e:
                print(f"download image error: {e}")
                img = None
            try:
                await buffer_queue.put(img)
            except asyncio.CancelledError:
                if isinstance(img, BytesIO):
                    try:
                        img.close()
                    except Exception:
                        pass
                raise

    workers = [asyncio.create_task(_worker()) for _ in range(worker_count)]

    async def _signal_done() -> None:
        await asyncio.gather(*workers, return_exceptions=True)
        await buffer_queue.put(None)

    coordinator = asyncio.create_task(_signal_done())

    sent = 0
    try:
        while True:
            img = await buffer_queue.get()
            if img is None:
                break
            try:
                if isinstance(img, BytesIO):
                    try:
                        await context.bot.send_photo(chat_id=chat_id, photo=img)
                        sent += 1
                    except RetryAfter as exc:
                        wait = max(1.0, float(exc.retry_after)) + 0.5
                        await asyncio.sleep(wait)
                        img.seek(0)
                        await context.bot.send_photo(chat_id=chat_id, photo=img)
                        sent += 1
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"send photo error: {e}")
            finally:
                if isinstance(img, BytesIO):
                    try:
                        img.close()
                    except Exception:
                        pass
        return sent
    except Exception as e:
        print(f"send_image_batch error: {e}")
        return sent
    finally:
        for t in workers:
            if not t.done():
                t.cancel()
        if not coordinator.done():
            coordinator.cancel()
        await asyncio.gather(*workers, coordinator, return_exceptions=True)
        while not buffer_queue.empty():
            leftover = buffer_queue.get_nowait()
            if isinstance(leftover, BytesIO):
                try:
                    leftover.close()
                except Exception:
                    pass


async def process_pinterest_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
    user_id: str,
    loading_message_id: int,
):

    search_timeout = pinterest_search_timeout_seconds()

    try:
        image_urls = await asyncio.wait_for(
            queued_pinterest_search(
                text,
                max_results=40,
            ),
            timeout=search_timeout,
        )

    except PinterestQueueFullError:
        print(f"Pinterest queue full for query: {text}")

        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=loading_message_id,
            )
        except Exception:
            pass

        wait_hint = estimate_pinterest_wait_seconds()
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🔴 در حال حاضر جستجوهای زیادی در صف هستند.\n"
                f"لطفاً حدود {wait_hint // 60 or 1} دقیقه دیگر دوباره تلاش کنید."
            ),
        )

        clear_state(chat_id)
        return

    except asyncio.TimeoutError:
        print(f"Pinterest search TIMEOUT for query: {text}")

        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=loading_message_id,
            )
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=chat_id,
            text="⏱️ جستجو بیش از حد طول کشید. لطفا دوباره تلاش کنید",
        )

        clear_state(chat_id)
        return

    except Exception as e:
        print(f"Pinterest search error: {e}")

        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=loading_message_id,
            )
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ خطا در جستجوی تصاویر Pinterest",
        )

        clear_state(chat_id)
        return

    image_urls = list(dict.fromkeys(image_urls))

    if not image_urls:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=loading_message_id,
            )
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ تصویری پیدا نشد",
        )

        clear_state(chat_id)
        return

    first_batch = image_urls[:SEND_BATCH_SIZE]

    sent_count = await send_image_batch(
        chat_id=chat_id,
        context=context,
        urls=first_batch,
    )

    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=loading_message_id,
        )
    except Exception:
        pass

    if sent_count == 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text=("❌ ارسال تصاویر با خطا مواجه شد"),
        )

        clear_state(chat_id)
        return

    await increment_pinterest_downloads(user_id)

    if SEND_BATCH_SIZE < len(image_urls):
        _pin_pagination_cache[str(chat_id)] = {
            "images": image_urls,
            "index": SEND_BATCH_SIZE,
        }
        await context.bot.send_message(
            chat_id=chat_id,
            text=("برای دریافت عکس‌های بیشتر روی دکمه زیر بزنید:"),
            reply_markup=build_more_keyboard(),
        )

    else:
        _pin_pagination_cache.pop(str(chat_id), None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ همه تصاویر ارسال شدند.",
        )

    clear_state(chat_id)


_pending_pinterest_searches: dict[str, int] = {}


async def handle_pinterest_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
):

    user_id = str(update.effective_user.id)

    async with user_action_lock(user_id, "pinterest_search", timeout_sec=10) as acquired:
        if not acquired:
            await update.message.reply_text("⏳ درخواست جستجوی قبلی شما در حال ثبت است. لطفاً صبر کنید.")
            return

        usage, vip_status = await asyncio.gather(
            get_pinterest_downloads(user_id),
            is_vip(user_id),
        )

        limit = get_limit(
            "pinterest_search",
            vip_status,
        )
        pending = _pending_pinterest_searches.get(user_id, 0)

        if usage + pending >= limit:
            await update.message.reply_text("❌ محدودیت روزانه شما به پایان رسیده است.")
            clear_state(chat_id)
            return

        clear_state(chat_id)
        _pending_pinterest_searches[user_id] = pending + 1

        wait_sec = estimate_pinterest_wait_seconds()
        if wait_sec > 45:
            msg = await update.message.reply_text(
                f"⏳ در صف جستجو هستید (تخمین انتظار: حدود {wait_sec // 60 or 1} دقیقه)..."
            )
        else:
            msg = await update.message.reply_text("⏳ در حال جستجوی تصاویر...")

        async def _tracked_search():
            try:
                await process_pinterest_search(
                    update=update,
                    context=context,
                    text=text,
                    chat_id=chat_id,
                    user_id=user_id,
                    loading_message_id=msg.message_id,
                )
            finally:
                cur = _pending_pinterest_searches.get(user_id, 0)
                if cur <= 1:
                    _pending_pinterest_searches.pop(user_id, None)
                else:
                    _pending_pinterest_searches[user_id] = cur - 1

        # مهم:
        # handler فوری آزاد می‌شود
        track_task(
            _tracked_search(),
            name=f"pinterest_search_{chat_id}",
        )


async def process_more_pins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query
    pin_key = str(query.message.chat_id)
    user_id = str(query.from_user.id) if query.from_user else pin_key

    async with user_action_lock(user_id, "more_pins", timeout_sec=60) as acquired:
        if not acquired:
            await context.bot.send_message(
                chat_id=pin_key,
                text="⏳ درخواست قبلی شما در حال ارسال است. لطفاً صبر کنید.",
            )
            return

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        cached_pin = _pin_pagination_cache.get(pin_key)
        images = (cached_pin or {}).get("images") or []
        index = (cached_pin or {}).get("index", 0)

        if not images:
            await context.bot.send_message(
                chat_id=pin_key,
                text="❌ داده‌ای یافت نشد",
            )
            return

        next_batch = images[index : index + SEND_BATCH_SIZE]

        if not next_batch:
            await context.bot.send_message(
                chat_id=pin_key,
                text="✅ همه تصاویر ارسال شدند",
            )
            return

        msg = await context.bot.send_message(
            chat_id=pin_key,
            text="⏳ در حال ارسال...",
        )

        sent_count = await send_image_batch(
            pin_key,
            context,
            next_batch,
        )

        try:
            await msg.delete()
        except Exception:
            pass

        if sent_count == 0:
            await context.bot.send_message(
                chat_id=pin_key,
                text="❌ خطا در ارسال تصاویر",
            )
            return

        next_index = index + SEND_BATCH_SIZE
        if next_index < len(images):
            _pin_pagination_cache[pin_key] = {
                "images": images,
                "index": next_index,
            }
            await context.bot.send_message(
                chat_id=pin_key,
                text="برای تصاویر بیشتر روی دکمه زیر بزنید:",
                reply_markup=build_more_keyboard(),
            )
        else:
            _pin_pagination_cache.pop(pin_key, None)
            await context.bot.send_message(
                chat_id=pin_key,
                text="✅ همه تصاویر ارسال شدند",
            )


async def handle_more_pins_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await safe_answer_query(query)

    track_task(
        process_more_pins(
            update,
            context,
        ),
        name=f"pinterest_more_{query.message.chat_id}",
    )
