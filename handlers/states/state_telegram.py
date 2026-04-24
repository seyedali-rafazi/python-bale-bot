# handlers/states/state_telegram.py

import re
import asyncio
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state

# --- تنظیمات صف ---
# تعداد پردازش‌های همزمان (می‌توانید به 2 یا 3 افزایش دهید)
MAX_CONCURRENT = 1
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
waiting_count = 0  # تعداد افراد حاضر در صف


async def fetch_url_background(url: str):
    response = await asyncio.to_thread(requests.get, url)
    return response


async def handle_telegram_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    global waiting_count

    # محاسبه موقعیت فعلی در صف
    current_position = waiting_count
    waiting_count += 1  # اضافه شدن کاربر جدید به صف

    if current_position >= MAX_CONCURRENT:
        # اگر ظرفیت پر باشد، کاربر در صف می‌ماند
        queue_number = current_position - MAX_CONCURRENT + 1
        await update.message.reply_text(
            f"⏳ ربات شلوغ است. شما در صف قرار گرفتید (نفر $ {queue_number} $ در صف). لطفاً صبور باشید..."
        )
    else:
        await update.message.reply_text("⏳ در حال پردازش درخواست شما ...")

    try:
        # ورود به دروازه پردازش (اگر پر باشد، کدهای زیر در اینجا متوقف می‌شوند تا نوبت کاربر برسد)
        async with processing_semaphore:
            waiting_count -= 1  # کاربر از صف خارج و وارد پردازش شد

            # اگر کاربر قبلاً در صف بوده، به او اطلاع می‌دهیم که نوبتش رسیده
            if current_position >= MAX_CONCURRENT:
                await update.message.reply_text(
                    "✅ نوبت شما رسید! در حال دریافت اطلاعات..."
                )

            # ---------------------------------------------------------
            # منطق اصلی کدهای شما از اینجا شروع می‌شود
            # ---------------------------------------------------------
            if step == "waiting_tg_single":
                link = text.strip()
                try:
                    embed_url = link + "?embed=1"
                    res = await fetch_url_background(embed_url)
                    soup = BeautifulSoup(res.text, "html.parser")

                    msg_div = soup.find("div", class_="tgme_widget_message_text")
                    msg_text = (
                        msg_div.get_text(separator="\n").strip() if msg_div else ""
                    )

                    video_url = None
                    video_tag = soup.find("video")
                    if video_tag:
                        if video_tag.get("src"):
                            video_url = video_tag["src"]
                        else:
                            source_tag = video_tag.find("source")
                            if source_tag and source_tag.get("src"):
                                video_url = source_tag["src"]

                    photo_url = None
                    if not video_url:
                        photo_wrap = soup.find(
                            "a", class_="tgme_widget_message_photo_wrap"
                        )
                        if photo_wrap and photo_wrap.get("style"):
                            match = re.search(
                                r"background-image:url\('([^']+)'\)",
                                photo_wrap["style"],
                            )
                            if match:
                                photo_url = match.group(1)

                    caption = msg_text if len(msg_text) <= 1024 else ""

                    if video_url:
                        await update.message.reply_video(
                            video=video_url, caption=caption
                        )
                    elif photo_url:
                        await update.message.reply_photo(
                            photo=photo_url, caption=caption
                        )
                    elif not msg_text:
                        await update.message.reply_text(
                            "❌ محتوایی در این لینک یافت نشد (احتمالاً فایل سندی است که از وب قابل دریافت نیست)."
                        )

                    if msg_text and (
                        not (video_url or photo_url) or len(msg_text) > 1024
                    ):
                        await update.message.reply_text(msg_text)

                except Exception as e:
                    print(f"Telegram Scraping Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در دریافت! ممکن است حجم ویدیو بالا باشد یا لینک معتبر نباشد."
                    )

                set_state(chat_id, "")

            elif step == "waiting_tg_latest":
                channel_id = text.strip().replace("@", "").split("/")[-1]
                try:
                    url = f"https://t.me/s/{channel_id}"
                    res = await fetch_url_background(url)
                    soup = BeautifulSoup(res.text, "html.parser")

                    messages = soup.find_all("div", class_="tgme_widget_message")
                    latest_messages = messages[-5:]

                    if not latest_messages:
                        await update.message.reply_text(
                            "❌ پیامی یافت نشد! مطمئن شوید آیدی صحیح است و کانال عمومی می‌باشد."
                        )
                    else:
                        for msg in latest_messages:
                            msg_div = msg.find("div", class_="tgme_widget_message_text")
                            msg_text = (
                                msg_div.get_text(separator="\n").strip()
                                if msg_div
                                else ""
                            )

                            has_video = bool(msg.find("video"))
                            if has_video:
                                msg_text = f"*(یک ویدیو در این پیام وجود داشت که برای کاهش بار سرور ارسال نشد)*\n\n{msg_text}"

                            photo_url = None
                            if not has_video:
                                photo_wrap = msg.find(
                                    "a", class_="tgme_widget_message_photo_wrap"
                                )
                                if photo_wrap and photo_wrap.get("style"):
                                    match = re.search(
                                        r"background-image:url\('([^']+)'\)",
                                        photo_wrap["style"],
                                    )
                                    if match:
                                        photo_url = match.group(1)

                            caption = msg_text if len(msg_text) <= 1024 else ""

                            try:
                                if photo_url:
                                    await update.message.reply_photo(
                                        photo=photo_url, caption=caption
                                    )

                                if msg_text and (not photo_url or len(msg_text) > 1024):
                                    await update.message.reply_text(
                                        msg_text, parse_mode="Markdown"
                                    )

                            except Exception as send_err:
                                print(f"Error sending media: {send_err}")
                                if msg_text:
                                    await update.message.reply_text(
                                        msg_text, parse_mode="Markdown"
                                    )

                except Exception as e:
                    print(f"Telegram Latest Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در خواندن کانال! ممکن است آیدی اشتباه باشد."
                    )

                set_state(chat_id, "")

    except Exception as general_err:
        print(f"Queue/Processing Error: {general_err}")
        # در صورت بروز خطای پیش‌بینی نشده، کاربر از صف خارج شده است (چون در بلاک try است)
        await update.message.reply_text("❌ خطای سیستمی رخ داد. لطفاً مجدداً تلاش کنید.")
