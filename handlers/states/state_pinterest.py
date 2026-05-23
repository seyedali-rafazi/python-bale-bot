# handlers/states/state_pinterest.py

import asyncio
from io import BytesIO
from typing import List, Optional

import aiohttp
from services.http_client import get_http_session

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)

from telegram.ext import ContextTypes

from core.state_manager import set_state

from core.database import (
    get_pinterest_downloads,
    increment_pinterest_downloads,
    is_vip,
)

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

download_semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

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


async def get_image_bytes(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
) -> Optional[BytesIO]:

    async with download_semaphore:
        for attempt in range(3):
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=25),
                    allow_redirects=True,
                    ssl=False,
                ) as res:
                    if res.status in (429, 503) and attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    if res.status != 200:
                        if attempt < 2:
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        return None

                    content_type = res.headers.get("Content-Type", "").lower()

                    if "image" not in content_type:
                        return None

                    bio = BytesIO()

                    async for chunk in res.content.iter_chunked(65536):
                        bio.write(chunk)

                    bio.seek(0)
                    bio.name = "pinterest.jpg"

                    return bio

            except Exception as e:
                print(f"download image error (try {attempt + 1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                return None
        return None


async def fetch_image_bytes(
    urls: List[str],
) -> List[BytesIO]:

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

    session = await get_http_session()
    tasks = [
        get_image_bytes(
            session,
            url,
            headers=headers,
        )
        for url in urls
    ]

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    images = []

    for item in results:
        if isinstance(item, BytesIO):
            images.append(item)

    return images


async def send_image_batch(
    chat_id: str,
    context: ContextTypes.DEFAULT_TYPE,
    urls: List[str],
) -> int:

    try:
        images = await fetch_image_bytes(urls)

        if not images:
            return 0

        sent = 0

        for img in images[:10]:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=img,
                )

                sent += 1

            except Exception as e:
                print(f"send photo error: {e}")

        return sent

    except Exception as e:
        print(f"send_image_batch error: {e}")
        return 0


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

        set_state(chat_id, "")
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

        set_state(chat_id, "")
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

        set_state(chat_id, "")
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

        set_state(chat_id, "")
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

        set_state(chat_id, "")
        return

    await increment_pinterest_downloads(user_id)

    context.user_data["pin_images"] = image_urls

    context.user_data["pin_index"] = SEND_BATCH_SIZE

    if SEND_BATCH_SIZE < len(image_urls):
        await context.bot.send_message(
            chat_id=chat_id,
            text=("برای دریافت عکس‌های بیشتر روی دکمه زیر بزنید:"),
            reply_markup=build_more_keyboard(),
        )

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ همه تصاویر ارسال شدند.",
        )

    set_state(chat_id, "")


async def handle_pinterest_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
):

    user_id = str(update.effective_user.id)

    usage = await get_pinterest_downloads(user_id)

    limit = get_limit(
        "pinterest_search",
        await is_vip(user_id),
    )

    if usage >= limit:
        await update.message.reply_text(("❌ محدودیت روزانه شما به پایان رسیده است."))

        set_state(chat_id, "")
        return

    wait_sec = estimate_pinterest_wait_seconds()
    if wait_sec > 45:
        msg = await update.message.reply_text(
            f"⏳ در صف جستجو هستید (تخمین انتظار: حدود {wait_sec // 60 or 1} دقیقه)..."
        )
    else:
        msg = await update.message.reply_text("⏳ در حال جستجوی تصاویر...")

    # مهم:
    # handler فوری آزاد می‌شود
    asyncio.create_task(
        process_pinterest_search(
            update=update,
            context=context,
            text=text,
            chat_id=chat_id,
            user_id=user_id,
            loading_message_id=msg.message_id,
        )
    )


async def process_more_pins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    images = context.user_data.get("pin_images", [])

    index = context.user_data.get("pin_index", 0)

    if not images:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ داده‌ای یافت نشد",
        )

        return

    next_batch = images[index : index + SEND_BATCH_SIZE]

    if not next_batch:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ همه تصاویر ارسال شدند",
        )

        return

    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⏳ در حال ارسال...",
    )

    sent_count = await send_image_batch(
        query.message.chat_id,
        context,
        next_batch,
    )

    try:
        await msg.delete()
    except Exception:
        pass

    if sent_count == 0:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ خطا در ارسال تصاویر",
        )

        return

    context.user_data["pin_index"] = index + SEND_BATCH_SIZE

    if context.user_data["pin_index"] < len(images):
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="برای تصاویر بیشتر روی دکمه زیر بزنید:",
            reply_markup=build_more_keyboard(),
        )

    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ همه تصاویر ارسال شدند",
        )


async def handle_more_pins_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    asyncio.create_task(
        process_more_pins(
            update,
            context,
        )
    )
