# handlers/states/state_pinterest.py


import asyncio
import aiohttp
from io import BytesIO
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.database import get_pinterest_downloads, increment_pinterest_downloads, is_vip
from services.pinterest import search_pinterest_images
from core.limits import get_limit


# محدود کردن تعداد دانلودهای همزمان کل ربات
download_semaphore = asyncio.Semaphore(5)


async def get_image_bytes(session, url):
    async with download_semaphore:
        try:
            async with session.get(url, timeout=5) as res:
                if res.status == 200:
                    data = await res.read()
                    return BytesIO(data)
        except:
            pass
        return None


async def handle_pinterest_state(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: str
):
    user_id = str(update.effective_user.id)

    usage = get_pinterest_downloads(user_id)
    limit = 30 if is_vip(user_id) else 5

    if usage >= limit:
        await update.message.reply_text(
            "❌ محدودیت روزانه شما به پایان رسیده است . محدودیت ها 12 شب به وقت تهران ریست میشود . کاربران رایگان میتوانند با خرید اشتراک محدودیت خودشون افزایش بدهند!"
        )
        set_state(chat_id, "")
        return

    msg = await update.message.reply_text("⏳ در حال جستجو و ارسال تصاویر...")

    images_urls = search_pinterest_images(text, max_results=50)

    if not images_urls:
        await msg.edit_text("❌ تصویری یافت نشد. کلمه دیگری امتحان کنید.")
        set_state(chat_id, "")
        return

    sent_count = 0
    current_index = 0

    async with aiohttp.ClientSession() as session:
        for url in images_urls:
            if sent_count >= 5:  # تعداد عکسی که می‌خواهیم ارسال کنیم
                break

            img_bytes = await get_image_bytes(session, url)
            if img_bytes:
                try:
                    await context.bot.send_photo(chat_id=chat_id, photo=img_bytes)
                    sent_count += 1
                except Exception as e:
                    print(f"Error sending individual photo: {e}")

            current_index += 1

    await msg.delete()

    if sent_count == 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ خطا در دانلود و ارسال تصاویر. کلمه دیگری تست کنید.",
        )
        set_state(chat_id, "")
        return

    increment_pinterest_downloads(user_id)
    context.user_data["pin_images"] = images_urls
    context.user_data["pin_index"] = current_index

    if context.user_data["pin_index"] < len(images_urls):
        keyboard = [
            [InlineKeyboardButton("➕ عکس‌های بیشتر", callback_data="more_pins")]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="برای دریافت عکس‌های بیشتر کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ تمام عکس‌های مرتبط با این موضوع ارسال شد. لطفاً موضوع جدیدی سرچ کنید.",
        )

    set_state(chat_id, "")


async def handle_more_pins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    usage = get_pinterest_downloads(user_id)
    vip = is_vip(user_id)
    limit = get_limit("pinterest_search", vip)

    if usage >= limit:
        await query.edit_message_text("❌ محدودیت روزانه شما به پایان رسیده است!")
        return

    await query.message.delete()

    msg = await context.bot.send_message(
        chat_id=query.message.chat_id, text="⏳ در حال دریافت تصاویر بعدی..."
    )

    images = context.user_data.get("pin_images", [])
    index = context.user_data.get("pin_index", 0)

    if index >= len(images):
        await msg.edit_text(
            "✅ تمام عکس‌های مرتبط با این موضوع ارسال شد. لطفاً موضوع جدیدی سرچ کنید."
        )
        return

    sent_count = 0
    current_index = index

    async with aiohttp.ClientSession() as session:
        for url in images[index:]:
            if sent_count >= 5:
                break

            img_bytes = await get_image_bytes(session, url)
            if img_bytes:
                try:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id, photo=img_bytes
                    )
                    sent_count += 1
                except Exception as e:
                    print(f"Error sending individual photo: {e}")

            current_index += 1

    await msg.delete()

    if sent_count == 0:
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="❌ تصاویر بعدی قابل دریافت نیستند."
        )
        return

    increment_pinterest_downloads(user_id)
    context.user_data["pin_index"] = current_index

    if context.user_data["pin_index"] < len(images):
        keyboard = [
            [InlineKeyboardButton("➕ عکس‌های بیشتر", callback_data="more_pins")]
        ]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="برای دریافت عکس‌های بیشتر کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ تمام عکس‌های مرتبط با این موضوع ارسال شد. لطفاً موضوع جدیدی سرچ کنید.",
        )
