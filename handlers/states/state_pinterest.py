# handlers/states/state_pinterest.py

import asyncio
import aiohttp
from io import BytesIO
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.database import (
    get_pinterest_downloads,
    increment_pinterest_downloads,
    is_vip,
)
from core.limits import get_limit
from services.pinterest_queue import queued_pinterest_search


download_semaphore = asyncio.Semaphore(5)
SEND_BATCH_SIZE = 5


def build_more_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("➕ عکس‌های بیشتر", callback_data="more_pins")]]
    )


async def get_image_bytes(
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[BytesIO]:
    async with download_semaphore:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
            ) as res:
                print(f"image download status={res.status} url={url}")

                if res.status != 200:
                    return None

                data = await res.read()

                if not data:
                    return None

                content_type = res.headers.get("Content-Type", "").lower()

                if "image" not in content_type:
                    if len(data) < 500:
                        return None

                bio = BytesIO(data)
                bio.name = "pinterest.jpg"
                bio.seek(0)

                return bio

        except Exception as e:
            print(f"get_image_bytes error: {e} url={url}")
            return None


async def fetch_image_bytes(urls: List[str]) -> List[BytesIO]:
    connector = aiohttp.TCPConnector(limit=10, ssl=False)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.pinterest.com/",
        "Accept": ("image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"),
    }

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers,
    ) as session:
        tasks = [get_image_bytes(session, url) for url in urls]

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

    sent_count = 0

    images = await fetch_image_bytes(urls)

    print(f"Sending batch of {len(urls)} urls")

    for img in images:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=img,
            )

            sent_count += 1

        except Exception as e:
            print(f"send_photo error: {e}")

    return sent_count


async def process_pinterest_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
    user_id: str,
    loading_message_id: int,
):
    try:
        image_urls = await queued_pinterest_search(
            text,
            max_results=40,
        )

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

    print(f"Pinterest found {len(image_urls)} image urls")

    if image_urls:
        print("Sample urls:", image_urls[:5])

    # حذف duplicate ها
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
        chat_id,
        context,
        first_batch,
    )

    # حذف loading message
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
            text=("❌ دانلود یا ارسال تصاویر با خطا مواجه شد. لطفاً دوباره تلاش کنید."),
        )

        set_state(chat_id, "")
        return

    await increment_pinterest_downloads(user_id)

    context.user_data["pin_images"] = image_urls
    context.user_data["pin_index"] = SEND_BATCH_SIZE

    if SEND_BATCH_SIZE < len(image_urls):
        await context.bot.send_message(
            chat_id=chat_id,
            text="برای دریافت عکس‌های بیشتر روی دکمه زیر بزنید:",
            reply_markup=build_more_keyboard(),
        )

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ همه تصاویر مرتبط ارسال شدند.",
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
        await update.message.reply_text(
            (
                "❌ محدودیت روزانه شما به پایان رسیده است.\n"
                "محدودیت‌ها ساعت ۱۲ شب به وقت تهران ریست می‌شوند."
            )
        )

        set_state(chat_id, "")
        return

    msg = await update.message.reply_text("⏳ در حال جستجوی تصاویر Pinterest...")

    # اجرای background task
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

    # مهم:
    # handler فوراً آزاد می‌شود
    return


async def handle_more_pins_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    user_id = str(update.effective_user.id)

    usage = await get_pinterest_downloads(user_id)

    limit = get_limit(
        "pinterest_search",
        await is_vip(user_id),
    )

    if usage >= limit:
        await query.edit_message_text("❌ محدودیت روزانه شما به پایان رسیده است!")
        return

    images = context.user_data.get("pin_images", [])

    index = context.user_data.get("pin_index", 0)

    if not images or index >= len(images):
        try:
            await query.edit_message_text("✅ همه تصاویر این جستجو قبلاً ارسال شده‌اند.")

        except Exception:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="✅ همه تصاویر این جستجو قبلاً ارسال شده‌اند.",
            )

        return

    try:
        await query.message.delete()
    except Exception:
        pass

    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⏳ در حال دریافت عکس‌های بیشتر...",
    )

    next_batch = images[index : index + SEND_BATCH_SIZE]

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
            text=("❌ تصاویر بعدی قابل ارسال نیستند. لطفاً جستجوی جدید انجام دهید."),
        )

        return

    await increment_pinterest_downloads(user_id)

    context.user_data["pin_index"] = index + SEND_BATCH_SIZE

    if context.user_data["pin_index"] < len(images):
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="برای دریافت عکس‌های بیشتر روی دکمه زیر بزنید:",
            reply_markup=build_more_keyboard(),
        )

    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ تمام تصاویر مرتبط با این موضوع ارسال شد.",
        )
