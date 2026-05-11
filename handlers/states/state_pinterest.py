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
from services.pinterest import search_pinterest_images


download_semaphore = asyncio.Semaphore(5)
SEND_BATCH_SIZE = 5


async def get_image_bytes(
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[BytesIO]:
    async with download_semaphore:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as res:
                if res.status != 200:
                    return None

                content_type = res.headers.get("Content-Type", "")
                if "image" not in content_type.lower():
                    return None

                data = await res.read()
                if not data:
                    return None

                bio = BytesIO(data)
                bio.name = "pinterest.jpg"
                bio.seek(0)
                return bio

        except Exception as e:
            print(f"get_image_bytes error: {e}")
            return None


async def fetch_images_bytes(
    urls: List[str],
) -> List[BytesIO]:
    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [get_image_bytes(session, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    images = []
    for item in results:
        if isinstance(item, BytesIO):
            images.append(item)
    return images


def build_more_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("➕ عکس‌های بیشتر", callback_data="more_pins")]]
    return InlineKeyboardMarkup(keyboard)


async def send_image_batch(
    chat_id: str,
    context: ContextTypes.DEFAULT_TYPE,
    urls: List[str],
) -> int:
    sent_count = 0
    images = await fetch_images_bytes(urls)

    for img in images:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=img)
            sent_count += 1
        except Exception as e:
            print(f"Error sending photo: {e}")

    return sent_count


async def handle_pinterest_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
):
    user_id = str(update.effective_user.id)

    usage = get_pinterest_downloads(user_id)
    limit = get_limit("pinterest_search", is_vip(user_id))

    if usage >= limit:
        await update.message.reply_text(
            "❌ محدودیت روزانه شما به پایان رسیده است. محدودیت‌ها ساعت ۱۲ شب به وقت تهران ریست می‌شوند."
        )
        set_state(chat_id, "")
        return

    msg = await update.message.reply_text("⏳ در حال جستجو در Pinterest...")

    try:
        image_urls = await search_pinterest_images(text, max_results=40)
    except Exception as e:
        print(f"Pinterest search error: {e}")
        image_urls = []

    if not image_urls:
        await msg.edit_text("❌ تصویری از Pinterest پیدا نشد. عبارت دیگری امتحان کنید.")
        set_state(chat_id, "")
        return

    # حذف تکراری‌ها
    deduped_urls = list(dict.fromkeys(image_urls))

    first_batch = deduped_urls[:SEND_BATCH_SIZE]
    sent_count = await send_image_batch(chat_id, context, first_batch)

    try:
        await msg.delete()
    except:
        pass

    if sent_count == 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ خطا در دانلود یا ارسال تصاویر. لطفاً عبارت دیگری تست کنید.",
        )
        set_state(chat_id, "")
        return

    increment_pinterest_downloads(user_id)

    context.user_data["pin_images"] = deduped_urls
    context.user_data["pin_index"] = SEND_BATCH_SIZE

    if SEND_BATCH_SIZE < len(deduped_urls):
        await context.bot.send_message(
            chat_id=chat_id,
            text="برای دریافت عکس‌های بیشتر کلیک کنید:",
            reply_markup=build_more_keyboard(),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ تمام عکس‌های مرتبط ارسال شد. موضوع جدیدی جستجو کنید.",
        )

    set_state(chat_id, "")


async def handle_more_pins_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    usage = get_pinterest_downloads(user_id)
    limit = get_limit("pinterest_search", is_vip(user_id))

    if usage >= limit:
        await query.edit_message_text("❌ محدودیت روزانه شما به پایان رسیده است!")
        return

    images = context.user_data.get("pin_images", [])
    index = context.user_data.get("pin_index", 0)

    if not images or index >= len(images):
        try:
            await query.edit_message_text(
                "✅ تمام عکس‌های مرتبط با این موضوع ارسال شده است."
            )
        except:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="✅ تمام عکس‌های مرتبط با این موضوع ارسال شده است.",
            )
        return

    try:
        await query.message.delete()
    except:
        pass

    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⏳ در حال دریافت تصاویر بیشتر از Pinterest...",
    )

    next_batch = images[index : index + SEND_BATCH_SIZE]
    sent_count = await send_image_batch(query.message.chat_id, context, next_batch)

    try:
        await msg.delete()
    except:
        pass

    if sent_count == 0:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ تصاویر بعدی قابل دریافت نیستند. لطفاً جستجوی جدید انجام دهید.",
        )
        return

    increment_pinterest_downloads(user_id)
    context.user_data["pin_index"] = index + SEND_BATCH_SIZE

    if context.user_data["pin_index"] < len(images):
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="برای دریافت عکس‌های بیشتر کلیک کنید:",
            reply_markup=build_more_keyboard(),
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ تمام عکس‌های مرتبط با این موضوع ارسال شد. لطفاً موضوع جدیدی جستجو کنید.",
        )
