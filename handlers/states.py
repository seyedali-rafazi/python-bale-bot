# handlers/states.py

import os
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import get_state, set_state
from core.constants import *
from core.keyboards import get_yt_format_keyboard
from services.youtube import (
    download_youtube_video,
    download_youtube_audio,
    search_yt_videos,
    MAX_TG_VIDEO_SIZE,
)
from services.instagram import download_instagram
from services.book import get_dbooks_download_url, download_pdf
from services.ai import ask_chatbot, perform_ocr, text_to_speech, generate_image
import shutil
from services.music import download_spotify_track, search_and_download_music


async def send_video_safe(context, chat_id, file_path, update):
    """ارسال ویدیو با چک حجم - اگه بزرگ بود به عنوان document میفرسته"""
    file_size = os.path.getsize(file_path)
    try:
        if file_size <= MAX_TG_VIDEO_SIZE:
            with open(file_path, "rb") as vid:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=vid,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=60,
                )
        else:
            await update.message.reply_text(
                f"⚠️ حجم ویدیو ({file_size // (1024 * 1024)} مگابایت) بیشتر از حد مجاز تلگرامه. به صورت فایل ارسال میشه..."
            )
            with open(file_path, "rb") as vid:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=vid,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=60,
                )
    except Exception as e:
        raise e


async def process_state_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get("step")

    # بازگشت سریع به منو (جایگزین دکمه‌هایی که کیبورد را دور میزنند)
    if text in ["0", "لغو", "شروع"]:
        from .commands import cmd_start

        await cmd_start(update, context)
        return

    if step == "waiting_book_selection":
        if text.startswith("📥 دانلود شماره "):
            try:
                index = int(text.replace("📥 دانلود شماره ", "").strip()) - 1
                books = state_data.get("books", [])
                selected_book = books[index]

                await update.message.reply_text(
                    f"⏳ در حال دانلود PDF:\n**{selected_book['title']}**..."
                )

                dl_link = selected_book["pdf_url"]
                if dl_link == "needs_fetch":
                    dl_link = await asyncio.to_thread(
                        get_dbooks_download_url, selected_book["id"]
                    )

                file_path = await asyncio.to_thread(
                    download_pdf, dl_link, selected_book["title"]
                )

                if file_path and os.path.exists(file_path):
                    await update.message.reply_text("✅ در حال آپلود...")
                    try:
                        with open(file_path, "rb") as doc:
                            await context.bot.send_document(
                                chat_id=chat_id, document=doc
                            )
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    await update.message.reply_text("❌ خطا در دانلود فایل PDF.")
            except Exception as e:
                await update.message.reply_text(
                    "❌ انتخاب نامعتبر است یا خطایی رخ داد."
                )
        return

    elif step == "waiting_yt_link":
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return
        set_state(chat_id, "waiting_yt_format", yt_url=text)
        await update.message.reply_text(
            "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
            reply_markup=get_yt_format_keyboard(),
        )
        return

    elif step == "waiting_yt_format":
        url = state_data.get("yt_url")
        if text == BTN_YT_VIDEO:
            await update.message.reply_text("⏳ در حال بررسی و دانلود ویدیو...")
            result = await asyncio.to_thread(download_youtube_video, url)

            if result == "TOO_LARGE":
                await update.message.reply_text(
                    "⚠️ حجم این ویدیو بیشتر از ۵۰ مگابایته و امکان ارسال نداره.\n"
                    "لطفاً ویدیوی کوتاه‌تری انتخاب کن."
                )
            elif result and os.path.exists(result):
                try:
                    with open(result, "rb") as vid:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=vid,
                            read_timeout=180,
                            write_timeout=180,
                            connect_timeout=60,
                        )
                finally:
                    if os.path.exists(result):
                        os.remove(result)
            else:
                await update.message.reply_text("❌ دانلود شکست خورد.")
            return

    elif step == "waiting_ig_link":
        if "instagram.com" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return
        await update.message.reply_text("⏳ در حال دانلود از اینستاگرام...")
        file_path = await asyncio.to_thread(download_instagram, text)
        if file_path and os.path.exists(file_path):
            try:
                if file_path.endswith(".mp4"):
                    with open(file_path, "rb") as vid:
                        await context.bot.send_video_safe(chat_id=chat_id, video=vid)
                else:
                    with open(file_path, "rb") as doc:
                        await context.bot.send_document(chat_id=chat_id, document=doc)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text("❌ دانلود شکست خورد.")
        return

    elif step == "waiting_ai_chat":
        await update.message.reply_text("⏳ در حال فکر کردن...")
        answer = await asyncio.to_thread(ask_chatbot, text)
        await update.message.reply_text(answer)
        return

    elif step == "waiting_ai_tts":
        await update.message.reply_text("⏳ در حال تبدیل متن به صدا...")
        file_path = await asyncio.to_thread(text_to_speech, text, chat_id)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(chat_id=chat_id, audio=aud)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text("❌ خطا در تولید صدا.")
        return

    elif step == "waiting_ai_image":
        await update.message.reply_text(
            "⏳ در حال تولید عکس (ممکن است کمی طول بکشد)..."
        )
        file_path = await asyncio.to_thread(generate_image, text, chat_id)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as img:
                    await context.bot.send_photo(chat_id=chat_id, photo=img)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text(
                "❌ خطا در تولید عکس. لطفاً متن دیگری را امتحان کنید."
            )
        return

    elif step == "waiting_music_search":
        await update.message.reply_text("⏳ در حال جستجو و دانلود بهترین نتیجه...")
        file_path, title = await asyncio.to_thread(
            search_and_download_music, text, chat_id
        )

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=aud, title=title
                    )
            finally:
                download_dir = f"temp_search_{chat_id}"
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir)
        else:
            await update.message.reply_text(
                "❌ متأسفانه آهنگی با این نام پیدا نشد یا خطایی رخ داد."
            )
        return

    elif step == "waiting_spotify_link":
        if "spotify.com" not in text:
            await update.message.reply_text("❌ لطفاً یک لینک معتبر اسپاتیفای بفرستید.")
            return

        await update.message.reply_text("⏳ در حال دانلود از اسپاتیفای...")
        file_path = await asyncio.to_thread(download_spotify_track, text, chat_id)

        if file_path and os.path.exists(file_path):
            try:
                title = os.path.basename(file_path).replace(".mp3", "")
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=aud, title=title
                    )
            finally:
                download_dir = f"temp_spotify_{chat_id}"
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir)
        else:
            await update.message.reply_text(
                "❌ دانلود شکست خورد. لطفاً لینک یک تک‌آهنگ (Track) را بفرستید."
            )
        return

    elif step == "waiting_tg_single":
        link = text.strip()
        await update.message.reply_text("⏳ در حال دریافت اطلاعات پیام...")
        try:
            import requests
            from bs4 import BeautifulSoup
            import re

            embed_url = link + "?embed=1"
            res = requests.get(embed_url)
            soup = BeautifulSoup(res.text, "html.parser")

            # دریافت متن پیام (کپشن)
            msg_div = soup.find("div", class_="tgme_widget_message_text")
            msg_text = msg_div.text if msg_div else ""

            # تلاش برای پیدا کردن لینک ویدیو
            video_url = None
            video_tag = soup.find("video")
            if video_tag:
                if video_tag.get("src"):
                    video_url = video_tag["src"]
                else:
                    source_tag = video_tag.find("source")
                    if source_tag and source_tag.get("src"):
                        video_url = source_tag["src"]

            # تلاش برای پیدا کردن لینک عکس
            photo_url = None
            if not video_url:
                photo_wrap = soup.find("a", class_="tgme_widget_message_photo_wrap")
                if photo_wrap and photo_wrap.get("style"):
                    match = re.search(
                        r"background-image:url\('([^']+)'\)", photo_wrap["style"]
                    )
                    if match:
                        photo_url = match.group(1)

            # ارسال نتیجه بر اساس محتوای پیدا شده
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
        # تمیز کردن ورودی (حذف @ یا لینک اضافی)
        channel_id = text.strip().replace("@", "").split("/")[-1]
        await update.message.reply_text("⏳ در حال دریافت ۵ پیام آخر کانال...")
        try:
            import requests
            from bs4 import BeautifulSoup
            import re

            # استفاده از /s/ برای دیدن تاریخچه کانال در وب
            url = f"https://t.me/s/{channel_id}"
            res = requests.get(url)
            soup = BeautifulSoup(res.text, "html.parser")

            # پیدا کردن تمام پیام‌ها
            messages = soup.find_all("div", class_="tgme_widget_message")
            latest_messages = messages[-5:]  # ۵ تای آخر

            if not latest_messages:
                await update.message.reply_text(
                    "❌ پیامی یافت نشد! مطمئن شوید آیدی صحیح است و کانال عمومی (Public) می‌باشد."
                )
            else:
                for msg in latest_messages:
                    # دریافت متن پیام
                    msg_div = msg.find("div", class_="tgme_widget_message_text")
                    msg_text = msg_div.text if msg_div else ""

                    # تلاش برای پیدا کردن لینک ویدیو
                    video_url = None
                    video_tag = msg.find("video")
                    if video_tag:
                        if video_tag.get("src"):
                            video_url = video_tag["src"]
                        else:
                            source_tag = video_tag.find("source")
                            if source_tag and source_tag.get("src"):
                                video_url = source_tag["src"]

                    # تلاش برای پیدا کردن لینک عکس
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

                    # کپشن تلگرام محدودیت کاراکتر دارد (۱۰۲۴ حرف)
                    safe_caption = msg_text[:1000] if msg_text else ""

                    # ارسال پیام
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
                        # اگر ارسال مدیا خطا داد، فقط متنش را بفرست
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

    elif step == "waiting_yt_last5_channel":
        channel = text.replace("@", "")
        url = f"https://www.youtube.com/@{channel}/videos"
        await update.message.reply_text("⏳ در حال دریافت لیست ویدیوها...")
        results = await asyncio.to_thread(search_yt_videos, url, 5)
        if not results:
            await update.message.reply_text("❌ کانال پیدا نشد یا ویدیویی ندارد.")
            return

        res_text = f"🎥 ۵ ویدیوی آخر کانال {channel}:\n\n"
        keyboard = []
        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])
        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_yt_selection", videos=results)
        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    elif step == "waiting_yt_global_search":
        await update.message.reply_text("⏳ در حال جستجو...")
        results = await asyncio.to_thread(search_yt_videos, text, 10)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🌍 نتایج جستجو برای `{text}`:\n\n"
        keyboard = []
        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            # چینش دکمه‌ها در دو ستون
            if i % 2 != 0:
                keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])
            else:
                keyboard[-1].append(KeyboardButton(f"📥 دانلود ویدیو {i}"))

        keyboard.append([KeyboardButton(BTN_BACK)])
        set_state(chat_id, "waiting_yt_selection", videos=results)
        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    elif step == "waiting_yt_ch_search_name":
        set_state(chat_id, "waiting_yt_ch_search_query", channel=text)
        await update.message.reply_text(
            "حالا کلمه کلیدی یا نام ویدیویی که در این کانال دنبالش هستید را بفرستید:"
        )
        return

    elif step == "waiting_yt_ch_search_query":
        channel = state_data.get("channel", "").replace("@", "")
        query = text
        await update.message.reply_text(
            "⏳ در حال جستجو در کانال (به دلیل محدودیت‌های یوتیوب ممکن است جستجوی جهانی با نام کانال انجام شود)..."
        )
        # استفاده از جستجوی ترکیبی نام کانال و کوئری
        search_query = f"{channel} {query}"
        results = await asyncio.to_thread(search_yt_videos, search_query, 5)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🔎 نتایج جستجو:\n\n"
        keyboard = []
        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])
        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_yt_selection", videos=results)
        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    elif step == "waiting_yt_selection":
        if text.startswith("📥 دانلود ویدیو "):
            try:
                index = int(text.replace("📥 دانلود ویدیو ", "").strip()) - 1
                videos = state_data.get("videos", [])

                if index < 0 or index >= len(videos):
                    await update.message.reply_text(
                        f"❌ شماره نامعتبر است. لطفاً عددی بین 1 تا {len(videos)} وارد کنید."
                    )
                    return

                selected_video = videos[index]
                await update.message.reply_text("⏳ در حال بررسی و دانلود ویدیو...")

                result = await asyncio.to_thread(
                    download_youtube_video, selected_video["url"]
                )

                if result == "TOO_LARGE":
                    await update.message.reply_text(
                        "⚠️ حجم این ویدیو بیشتر از ۵۰ مگابایته و امکان ارسال نداره.\n"
                        "لطفاً ویدیوی کوتاه‌تری انتخاب کن."
                    )
                elif result and os.path.exists(result):
                    try:
                        await update.message.reply_text("📤 در حال آپلود ویدیو...")
                        with open(result, "rb") as vid:
                            await context.bot.send_video(
                                chat_id=chat_id,
                                video=vid,
                                read_timeout=180,
                                write_timeout=180,
                                connect_timeout=60,
                            )
                        await update.message.reply_text("✅ ارسال موفق بود!")
                    except Exception as send_err:
                        print(f"❌ Send error: {send_err}")
                        await update.message.reply_text(
                            f"❌ خطا در ارسال: {str(send_err)}"
                        )
                    finally:
                        if os.path.exists(result):
                            os.remove(result)
                else:
                    await update.message.reply_text(
                        "❌ دانلود شکست خورد یا فایل پیدا نشد."
                    )

            except ValueError:
                await update.message.reply_text("❌ فرمت شماره اشتباه است.")
            except Exception as e:
                print(f"❌ Error: {e}")
                await update.message.reply_text(f"❌ خطا: {str(e)}")
        return

    elif step == "waiting_yt_link":
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        dl_format = state_data.get("format", "video")

        if dl_format == "video":
            await update.message.reply_text("⏳ در حال دانلود ویدیو...")
            file_path = await asyncio.to_thread(download_youtube_video, text)
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as vid:
                        await context.bot.send_video_safe(chat_id=chat_id, video=vid)
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                await update.message.reply_text("❌ دانلود شکست خورد.")
        elif dl_format == "audio":
            await update.message.reply_text("⏳ در حال استخراج صدا (MP3)...")
            file_path, title, perf = await asyncio.to_thread(
                download_youtube_audio, text
            )
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as aud:
                        await context.bot.send_audio(
                            chat_id=chat_id, audio=aud, title=title, performer=perf
                        )
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                await update.message.reply_text("❌ دانلود شکست خورد.")
        return

    if not step:
        await update.message.reply_text("لطفاً از منو استفاده کنید.")


async def process_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get("step") if state_data else None

    if step == "waiting_ai_ocr":
        await update.message.reply_text("⏳ در حال دانلود و پردازش عکس...")

        try:
            # بررسی اینکه کاربر عکس را عادی فرستاده یا به صورت فایل (Document)
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
            elif update.message.document:
                file_id = update.message.document.file_id
            else:
                await update.message.reply_text("❌ فرمت فایل پشتیبانی نمی‌شود.")
                return

            # دانلود عکس از سرور تلگرام
            file = await context.bot.get_file(file_id)
            file_path = f"temp_ocr_{chat_id}.jpg"
            await file.download_to_drive(file_path)

            # پردازش OCR
            extracted_text = await asyncio.to_thread(perform_ocr, file_path)

            # حذف فایل موقت
            if os.path.exists(file_path):
                os.remove(file_path)

            await update.message.reply_text(
                f"✅ **متن استخراج شده:**\n\n{extracted_text}"
            )

            # مهم: پاک کردن وضعیت کاربر تا ربات در حالت OCR گیر نکند
            set_state(chat_id, "")

        except Exception as e:
            await update.message.reply_text(f"❌ خطایی در پردازش عکس رخ داد: {e}")
            set_state(chat_id, "")

    else:
        await update.message.reply_text("متوجه نشدم. لطفاً از منو استفاده کنید.")
