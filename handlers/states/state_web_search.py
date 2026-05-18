# handlers/states/state_web_search.py

import os
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import get_state, set_state, clear_state
from services.web_scraper import create_single_file
import asyncio
from services.web_scraper import search_web
from core.database import (
    get_web_search_downloads,
    increment_web_search_downloads,
    is_vip,
)
from core.limits import get_limit


async def web_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = str(update.effective_chat.id)
    data = query.data

    index = int(data.split("_")[1])
    state = get_state(chat_id)

    urls = state.get("urls", [])
    if not urls or index >= len(urls):
        await query.message.reply_text(
            "❌ نشست شما منقضی شده است. لطفاً مجدداً جستجو کنید."
        )
        return

    # بررسی حد روزانه دانلود
    user_id = update.effective_user.id
    vip = await is_vip(user_id)

    # حد روزانه: 1 برای کاربران عادی، 20 برای VIP
    daily_limit = get_limit("web_search", vip)
    current_downloads = await get_web_search_downloads(user_id)

    if current_downloads >= daily_limit:
        await query.message.reply_text(
            f"❌ شما امروز به حد مجاز دانلود رسیده‌اید.\n\n"
            f"📊 محدودیت روزانه: {daily_limit} بار\n"
            f"🌟 برای افزایش حد، VIP شوید!"
        )
        return

    target_url = urls[index]
    wait_msg = await query.message.reply_text(
        "⏳ در حال پردازش و دریافت کل صفحه (ممکن است کمی طول بکشد)..."
    )

    os.makedirs("downloads", exist_ok=True)
    output_filename = f"downloads/page_{chat_id}_{int(time.time())}.html"

    success = await create_single_file(target_url, output_filename)

    if success:
        # افزایش تعداد دانلود پس از موفقیت
        new_count = await increment_web_search_downloads(user_id)

        await wait_msg.edit_text("✅ فایل آماده شد. در حال ارسال...")
        try:
            await context.bot.send_document(
                chat_id=chat_id,
                document=open(output_filename, "rb"),
                filename=f"WebPage_{index + 1}.html",
                caption=f"🔗 لینک اصلی: {target_url}\n\n📊 دانلود‌های امروز: {new_count}/{daily_limit}",
            )
        except Exception as e:
            print(f"Send Document Error: {e}")
            await wait_msg.edit_text("❌ خطا در ارسال فایل.")
    else:
        await wait_msg.edit_text(
            "❌ متاسفانه دریافت این صفحه با مشکل مواجه شد. (ممکن است سایت محافظت شده باشد)"
        )


async def handle_web_search_state(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: str
):
    state_data = get_state(chat_id)
    step = state_data.get("step")

    if step == "waiting_google_search_subject":
        # بخش جستجو با موضوع
        wait_msg = await update.message.reply_text("⏳ در حال جستجو...")

        # اجرای سرچ در ترد جداگانه
        results = await asyncio.to_thread(search_web, text, 10)

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

        # بررسی حد روزانه دانلود
        user_id = update.effective_user.id
        vip = await is_vip(user_id)

        # حد روزانه: 1 برای کاربران عادی، 20 برای VIP
        daily_limit = get_limit("web_search", vip)
        current_downloads = await get_web_search_downloads(user_id)

        if current_downloads >= daily_limit:
            await update.message.reply_text(
                f"❌ شما امروز به حد مجاز دانلود رسیده‌اید.\n\n"
                f"📊 محدودیت روزانه: {daily_limit} بار\n"
                f"🌟 برای افزایش حد، VIP شوید!"
            )
            clear_state(chat_id)
            return

        wait_msg = await update.message.reply_text(
            "⏳ در حال پردازش و دریافت صفحه (ممکن است کمی طول بکشد)..."
        )

        os.makedirs("downloads", exist_ok=True)
        output_filename = f"downloads/page_{chat_id}_{int(time.time())}.html"

        try:
            success = await create_single_file(url, output_filename)

            if success:
                # افزایش تعداد دانلود پس از موفقیت
                new_count = await increment_web_search_downloads(user_id)

                await wait_msg.edit_text("✅ فایل آماده شد. در حال ارسال...")
                try:
                    with open(output_filename, "rb") as f:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            filename="WebPage.html",
                            caption=f"🔗 لینک: {url}\n\n📊 دانلود‌های امروز: {new_count}/{daily_limit}",
                        )
                except Exception as e:
                    print(f"Send Document Error: {e}")
                    await wait_msg.edit_text("❌ خطا در ارسال فایل.")
            else:
                await wait_msg.edit_text(
                    "❌ متاسفانه دریافت این صفحه با مشکل مواجه شد.\n\n(ممکن است سایت محافظت شده باشد یا لینک اشتباه باشد)"
                )
        except Exception as e:
            print(f"Web Search Link Error: {e}")
            await update.message.reply_text(
                "❌ خطایی در پردازش درخواست رخ داد. لطفاً دوباره تلاش کنید."
            )
        finally:
            clear_state(chat_id)
