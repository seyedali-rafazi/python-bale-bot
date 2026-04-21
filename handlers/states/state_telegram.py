import re
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state


async def handle_telegram_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_tg_single":
        link = text.strip()
        await update.message.reply_text("⏳ در حال دریافت اطلاعات پیام...")
        try:
            embed_url = link + "?embed=1"
            res = requests.get(embed_url)
            soup = BeautifulSoup(res.text, "html.parser")

            msg_div = soup.find("div", class_="tgme_widget_message_text")
            msg_text = msg_div.text if msg_div else ""

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
                photo_wrap = soup.find("a", class_="tgme_widget_message_photo_wrap")
                if photo_wrap and photo_wrap.get("style"):
                    match = re.search(
                        r"background-image:url\('([^']+)'\)", photo_wrap["style"]
                    )
                    if match:
                        photo_url = match.group(1)

            if video_url:
                await update.message.reply_video(video=video_url, caption=msg_text)
            elif photo_url:
                await update.message.reply_photo(photo=photo_url, caption=msg_text)
            elif msg_text:
                await update.message.reply_text(msg_text)
            else:
                await update.message.reply_text("❌ محتوایی در این لینک یافت نشد.")

        except Exception as e:
            print(f"Telegram Scraping Error: {e}")
            await update.message.reply_text(
                "❌ خطا در دریافت پیام! ممکن است حجم ویدیو بسیار بالا باشد یا لینک معتبر نباشد."
            )

        set_state(chat_id, "")

    elif step == "waiting_tg_latest":
        channel_id = text.strip().replace("@", "").split("/")[-1]
        await update.message.reply_text("⏳ در حال دریافت ۵ پیام آخر کانال...")
        try:
            url = f"https://t.me/s/{channel_id}"
            res = requests.get(url)
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
                    msg_text = msg_div.text if msg_div else ""

                    video_url = None
                    video_tag = msg.find("video")
                    if video_tag:
                        if video_tag.get("src"):
                            video_url = video_tag["src"]
                        else:
                            source_tag = video_tag.find("source")
                            if source_tag and source_tag.get("src"):
                                video_url = source_tag["src"]

                    photo_url = None
                    if not video_url:
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

                    safe_caption = msg_text[:1000] if msg_text else ""

                    try:
                        if video_url:
                            await update.message.reply_video(
                                video=video_url, caption=safe_caption
                            )
                        elif photo_url:
                            await update.message.reply_photo(
                                photo=photo_url, caption=safe_caption
                            )
                        elif msg_text:
                            await update.message.reply_text(msg_text)
                    except Exception as send_err:
                        print(f"Error sending media: {send_err}")
                        if msg_text:
                            await update.message.reply_text(
                                f"*(فایل قابل ارسال نبود)*\n\n{msg_text}",
                                parse_mode="Markdown",
                            )

        except Exception as e:
            print(f"Telegram Latest Error: {e}")
            await update.message.reply_text(
                "❌ خطا در خواندن کانال! ممکن است آیدی اشتباه باشد."
            )

        set_state(chat_id, "")
