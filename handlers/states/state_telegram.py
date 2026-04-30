# handlers/states/state_telegram.py

import re
import asyncio
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state

# --- تنظیمات پردازش ---
# اسکرپ کردن تلگرام سبک است و سرور خود تلگرام فایل را دانلود می‌کند، پس ظرفیت می‌تواند بالاتر باشد
MAX_CONCURRENT = 10
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT)


async def fetch_url_background(url: str):
    # بهینه‌سازی مهم: اضافه کردن timeout برای جلوگیری از قفل شدن همیشگی تردها در صورت قطعی شبکه
    response = await asyncio.to_thread(requests.get, url, timeout=15)
    return response


async def handle_telegram_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    # محاسبه تعداد افراد در صف به روش ایمن
    waiters = len(processing_semaphore._waiters) if processing_semaphore._waiters else 0
    available = processing_semaphore._value

    if available == 0:
        await update.message.reply_text(
            f"⏳ ربات در حال حاضر مشغول است. شما در صف قرار گرفتید (نفر {waiters + 1} در صف). لطفاً صبور باشید..."
        )
    else:
        await update.message.reply_text("⏳ در حال دریافت اطلاعات از تلگرام...")

    try:
        async with processing_semaphore:
            if step == "waiting_tg_single":
                link = text.strip()
                try:
                    embed_url = link + "?embed=1"
                    res = await fetch_url_background(embed_url)

                    # پارس کردن HTML (به صورت غیرهمگام اجرا می‌شود تا ایونت لوپ را بلاک نکند)
                    soup = await asyncio.to_thread(
                        BeautifulSoup, res.text, "html.parser"
                    )

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

                except requests.exceptions.Timeout:
                    await update.message.reply_text(
                        "❌ ارتباط با سرور زمان‌بر شد. لطفاً دوباره تلاش کنید."
                    )
                except Exception as e:
                    print(f"Telegram Scraping Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در دریافت! ممکن است لینک معتبر نباشد یا محتوا خصوصی باشد."
                    )

            elif step == "waiting_tg_latest":
                channel_id = text.strip().replace("@", "").split("/")[-1]
                try:
                    url = f"https://t.me/s/{channel_id}"
                    res = await fetch_url_background(url)

                    soup = await asyncio.to_thread(
                        BeautifulSoup, res.text, "html.parser"
                    )
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

                except requests.exceptions.Timeout:
                    await update.message.reply_text(
                        "❌ ارتباط با سرور تلگرام قطع شد. لطفاً بعدا تلاش کنید."
                    )
                except Exception as e:
                    print(f"Telegram Latest Error: {e}")
                    await update.message.reply_text(
                        "❌ خطا در خواندن کانال! ممکن است آیدی اشتباه باشد."
                    )

    except Exception as general_err:
        print(f"Queue/Processing Error: {general_err}")
        await update.message.reply_text("❌ خطای سیستمی رخ داد. لطفاً مجدداً تلاش کنید.")

    finally:
        # اطمینان از خروج از استیت در هر شرایط (حتی ارورها)
        set_state(chat_id, "")
