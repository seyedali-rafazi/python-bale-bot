# handlers/states/state_web_search.py

import os
import time
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import async_get_state, set_state, clear_state
from core.task_utils import load_input_file, remove_file_async
from services.rate_limiter import user_action_lock
from services.web_scraper import async_search_web, create_single_file
import asyncio
from core.database import (
    get_web_search_downloads,
    increment_web_search_downloads,
    is_vip,
)
from core.limits import get_limit


async def _download_and_send_webpage(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    user_id: int,
    target_url: str,
    *,
    filename: str,
    caption_label: str,
    wait_text: str,
    fail_text: str,
) -> bool:
    """Check daily web-search limit, capture webpage as HTML, and send it to the user."""
    async with user_action_lock(user_id, "web_search_dl", timeout_sec=120) as acquired:
        if not acquired:
            await message.reply_text("⏳ درخواست قبلی شما هنوز در حال پردازش است. لطفاً صبر کنید.")
            return False

        vip, current_downloads = await asyncio.gather(
            is_vip(user_id),
            get_web_search_downloads(user_id),
        )
        daily_limit = get_limit("web_search", vip)

        if current_downloads >= daily_limit:
            await message.reply_text(
                f"❌ شما امروز به حد مجاز دانلود رسیده‌اید.\n\n"
                f"📊 محدودیت روزانه: {daily_limit} بار\n"
                f"🌟 برای افزایش حد، VIP شوید!"
            )
            return False

        wait_msg = await message.reply_text(wait_text)
        await asyncio.to_thread(os.makedirs, "downloads", exist_ok=True)
        output_filename = (
            f"downloads/page_{chat_id}_{int(time.time())}_{uuid.uuid4().hex[:6]}.html"
        )

        try:
            success = await create_single_file(target_url, output_filename)
            if not success:
                await wait_msg.edit_text(fail_text)
                return False

            new_count = await increment_web_search_downloads(user_id)
            await wait_msg.edit_text("✅ فایل آماده شد. در حال ارسال...")
            try:
                doc_input = await load_input_file(output_filename, filename=filename)
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc_input,
                    filename=filename,
                    caption=f"{caption_label}: {target_url}\n\n📊 دانلود‌های امروز: {new_count}/{daily_limit}",
                )
                return True
            except Exception as e:
                print(f"Send Document Error: {e}")
                await wait_msg.edit_text("❌ خطا در ارسال فایل.")
                return False
        except Exception as e:
            print(f"Web Search Download Error: {e}")
            try:
                await wait_msg.edit_text(
                    "❌ خطایی در پردازش درخواست رخ داد. لطفاً دوباره تلاش کنید."
                )
            except Exception:
                await message.reply_text(
                    "❌ خطایی در پردازش درخواست رخ داد. لطفاً دوباره تلاش کنید."
                )
            return False
        finally:
            await remove_file_async(output_filename)


async def web_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = str(update.effective_chat.id)
    data = query.data

    index = int(data.split("_")[1])
    state = await async_get_state(chat_id)

    urls = state.get("urls", [])
    if not urls or index >= len(urls):
        await query.message.reply_text(
            "❌ نشست شما منقضی شده است. لطفاً مجدداً جستجو کنید."
        )
        return

    target_url = urls[index]
    await _download_and_send_webpage(
        query.message,
        context,
        chat_id,
        update.effective_user.id,
        target_url,
        filename=f"WebPage_{index + 1}.html",
        caption_label="🔗 لینک اصلی",
        wait_text="⏳ در حال پردازش و دریافت کل صفحه (ممکن است کمی طول بکشد)...",
        fail_text="❌ متاسفانه دریافت این صفحه با مشکل مواجه شد. (ممکن است سایت محافظت شده باشد)",
    )


async def handle_web_search_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
    state_data: dict | None = None,
):
    if state_data is None:
        state_data = await async_get_state(chat_id)
    step = state_data.get("step")

    if step == "waiting_google_search_menu":
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های منوی جستجوی وب را انتخاب کنید."
        )
        return

    if step == "waiting_google_search_subject":
        # بخش جستجو با موضوع
        wait_msg = await update.message.reply_text("⏳ در حال جستجو...")

        # اجرای سرچ غیرهم‌زمان با کش و تایم‌اوت
        try:
            results = await async_search_web(text, 10)
        except Exception as e:
            print(f"Web Search Error: {e}")
            results = []

        if not results:
            await wait_msg.edit_text("❌ نتیجه‌ای یافت نشد یا خطایی رخ داد.")
            clear_state(chat_id)
            return

        # ذخیره لینک‌ها در context برای استفاده در دکمه‌های شیشه‌ای
        set_state(chat_id, "web_search_results", urls=[r["url"] for r in results])

        msg_text = "🌐 **نتایج جستجو:**\n\n"
        keyboard = []

        for i, res in enumerate(results):
            msg_text += f"{i + 1}. [{res['title']}]({res['url']})\n"
            # دکمه‌ها را دو تا دو تا می‌چینیم
            if i % 2 == 0:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"نتیجه {i + 1}", callback_data=f"webres_{i}"
                        )
                    ]
                )
            else:
                keyboard[-1].append(
                    InlineKeyboardButton(f"نتیجه {i + 1}", callback_data=f"webres_{i}")
                )

        await wait_msg.edit_text(
            msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    elif step == "waiting_google_search_link":
        # بخش دانلود فایل از لینک
        url = text.strip()

        # بررسی اینکه آیا لینک معتبر است
        if not url.startswith(("http://", "https://")):
            await update.message.reply_text(
                "❌ لینک باید با http:// یا https:// شروع شود.\n\nلطفاً یک لینک معتبر ارسال کنید:"
            )
            return

        try:
            await _download_and_send_webpage(
                update.message,
                context,
                chat_id,
                update.effective_user.id,
                url,
                filename="WebPage.html",
                caption_label="🔗 لینک",
                wait_text="⏳ در حال پردازش و دریافت صفحه (ممکن است کمی طول بکشد)...",
                fail_text="❌ متاسفانه دریافت این صفحه با مشکل مواجه شد.\n\n(ممکن است سایت محافظت شده باشد یا لینک اشتباه باشد)",
            )
        finally:
            clear_state(chat_id)
