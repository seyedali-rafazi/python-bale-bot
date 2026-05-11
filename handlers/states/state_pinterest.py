# handlers/states/state_pinterest.py


import asyncio
import aiohttp
import requests
from io import BytesIO
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.database import get_pinterest_downloads, increment_pinterest_downloads, is_vip
import re

# محدود کردن تعداد دانلودهای همزمان کل ربات
download_semaphore = asyncio.Semaphore(5)


# -------------------------------------------------------------
# تابع جدید برای اسکرپ مستقیم از پینترست (جایگزین داک‌داک‌گو)
# -------------------------------------------------------------
def search_pinterest_images(query, max_results=10):
    url = f"https://www.pinterest.com/search/pins/?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)

        # پینترست لینک عکس‌های باکیفیت (originals) را در سورس صفحه مخفی می‌کند
        # با استفاده از Regex این لینک‌ها را پیدا می‌کنیم
        image_urls = re.findall(
            r"https://i\.pinimg\.com/originals/[a-zA-Z0-9/_\-]+\.jpg", response.text
        )

        # حذف لینک‌های تکراری
        unique_urls = list(set(image_urls))

        return unique_urls[:max_results]

    except Exception as e:
        print(f"Error scraping Pinterest: {e}")
        return []


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

    msg = await update.message.reply_text("⏳ در حال جستجو مستقیم در پینترست...")

    images_urls = search_pinterest_images(text, max_results=50)

    if not images_urls:
        await msg.edit_text("❌ تصویری یافت نشد. کلمه دیگری امتحان کنید.")
        set_state(chat_id, "")
        return

    async with aiohttp.ClientSession() as session:
        tasks = [get_image_bytes(session, url) for url in images_urls[:10]]
        results = await asyncio.gather(*tasks)

    successful_images = [BytesIO(res.getvalue()) for res in results if res is not None]

    if not successful_images:
        await msg.edit_text("❌ خطا در دانلود تصاویر. کلمه دیگری تست کنید.")
        set_state(chat_id, "")
        return

    try:
        await msg.delete()

        # --- تغییر جدید: ارسال عکس‌ها به صورت تک‌تک ---
        for img_bytes in successful_images[:5]:
            await context.bot.send_photo(chat_id=chat_id, photo=img_bytes)
            # برای جلوگیری از خطای فلود تلگرام یه مکث خیلی کوتاه
            await asyncio.sleep(0.3)

        increment_pinterest_downloads(user_id)

        context.user_data["pin_images"] = images_urls
        context.user_data["pin_index"] = 10

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
    except Exception as e:
        print(f"Error: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="❌ ارسال تصاویر با مشکل مواجه شد."
        )
    finally:
        set_state(chat_id, "")


async def handle_more_pins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    usage = get_pinterest_downloads(user_id)
    limit = 30 if is_vip(user_id) else 5

    if usage >= limit:
        await query.edit_message_text("❌ محدودیت روزانه شما به پایان رسیده است!")
        return

    await query.message.delete()

    msg = await context.bot.send_message(
        chat_id=query.message.chat_id, text="⏳ در حال دریافت تصاویر..."
    )

    images = context.user_data.get("pin_images", [])
    index = context.user_data.get("pin_index", 0)

    if index >= len(images):
        await msg.edit_text(
            "✅ تمام عکس‌های مرتبط با این موضوع ارسال شد. لطفاً موضوع جدیدی سرچ کنید."
        )
        return

    async with aiohttp.ClientSession() as session:
        tasks = [get_image_bytes(session, url) for url in images[index : index + 10]]
        results = await asyncio.gather(*tasks)

    successful_images = [BytesIO(res.getvalue()) for res in results if res is not None]

    if not successful_images:
        await msg.edit_text("❌ تصاویر بعدی قابل دریافت نیستند.")
        return

    try:
        await msg.delete()

        # --- تغییر جدید: ارسال عکس‌ها به صورت تک‌تک ---
        for img_bytes in successful_images[:5]:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=img_bytes)
            await asyncio.sleep(0.3)

        increment_pinterest_downloads(user_id)
        context.user_data["pin_index"] = index + 10

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
    except Exception as e:
        print(f"Error: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="❌ خطا در ارسال."
        )
