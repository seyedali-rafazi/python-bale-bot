import asyncio
import aiohttp
from io import BytesIO
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.database import get_pinterest_downloads, increment_pinterest_downloads, is_vip
from services.pinterest import search_pinterest_images

# محدود کردن تعداد دانلودهای همزمان کل ربات (مثلا 10 دانلود همزمان)
download_semaphore = asyncio.Semaphore(5)


async def get_image_bytes(session, url):
    async with download_semaphore:  # اعمال محدودیت همزمانی
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
        await update.message.reply_text("❌ محدودیت روزانه شما به پایان رسیده است!")
        set_state(chat_id, "")
        return

    msg = await update.message.reply_text("⏳ در حال جستجو و دریافت تصاویر...")
    images_urls = search_pinterest_images(text, max_results=10)

    if not images_urls:
        await msg.edit_text("❌ تصویری یافت نشد. کلمه دیگری امتحان کنید.")
        set_state(chat_id, "")
        return

    media_group = []

    # دانلود همزمان همه عکس‌ها با رعایت سقف Semaphore
    async with aiohttp.ClientSession() as session:
        tasks = [get_image_bytes(session, url) for url in images_urls[:10]]
        results = await asyncio.gather(*tasks)

    # جدا کردن 5 عکس اول که با موفقیت دانلود شده‌اند
    successful_images = [BytesIO(res.getvalue()) for res in results if res is not None]

    for img_bytes in successful_images[:5]:
        media_group.append(InputMediaPhoto(media=img_bytes))

    if not media_group:
        await msg.edit_text("❌ خطا در دانلود تصاویر. کلمه دیگری تست کنید.")
        set_state(chat_id, "")
        return

    try:
        await msg.delete()
        await context.bot.send_media_group(chat_id=chat_id, media=media_group)
        increment_pinterest_downloads(user_id)

        context.user_data["pin_images"] = images_urls
        context.user_data["pin_index"] = 5

        keyboard = [
            [InlineKeyboardButton("➕ عکس‌های بیشتر", callback_data="more_pins")]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="برای دریافت عکس‌های بیشتر کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"Error: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="❌ ارسال تصاویر پشتیبانی نشد."
        )
    finally:
        set_state(chat_id, "")


async def handle_more_pins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال دریافت تصاویر...", show_alert=False)

    images = context.user_data.get("pin_images", [])
    index = context.user_data.get("pin_index", 0)

    if index >= len(images):
        await query.edit_message_text("❌ عکس بیشتری وجود ندارد.")
        return

    media_group = []

    async with aiohttp.ClientSession() as session:
        tasks = [get_image_bytes(session, url) for url in images[index : index + 5]]
        results = await asyncio.gather(*tasks)

    successful_images = [BytesIO(res.getvalue()) for res in results if res is not None]

    for img_bytes in successful_images[:5]:
        media_group.append(InputMediaPhoto(media=img_bytes))

    if not media_group:
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="❌ تصاویر بعدی قابل دریافت نیستند."
        )
        return

    try:
        await context.bot.send_media_group(
            chat_id=query.message.chat_id, media=media_group
        )
        context.user_data["pin_index"] = index + 5
    except Exception as e:
        print(f"Error: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="❌ خطا در ارسال."
        )
