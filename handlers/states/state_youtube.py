import os
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import BTN_YT_VIDEO, BTN_BACK
from core.keyboards import get_yt_format_keyboard
from services.youtube import (
    download_youtube_video,
    download_youtube_audio,
    search_yt_videos,
)


async def handle_youtube_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):

    if step == "waiting_yt_last5_channel":
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
                await update.message.reply_text(
                    "⏳ در حال بررسی و دانلود ویدیو (ممکن است زمان‌بر باشد)..."
                )

                result = await asyncio.to_thread(
                    download_youtube_video, selected_video["url"]
                )

                if result == "TOO_LARGE":
                    await update.message.reply_text(
                        "⚠️ حجم این ویدیو بیشتر از ۳۰۰ مگابایته و امکان پردازش نداره.\n"
                        "لطفاً ویدیوی کم‌حجم‌تری انتخاب کن."
                    )
                elif isinstance(result, list) and len(result) > 0:
                    try:
                        part_msg = (
                            f" (شامل {len(result)} پارت به دلیل حجم بالا)"
                            if len(result) > 1
                            else ""
                        )
                        await update.message.reply_text(
                            f"📤 در حال آپلود ویدیو{part_msg}..."
                        )

                        for idx, file_path in enumerate(result, 1):
                            if len(result) > 1:
                                await update.message.reply_text(
                                    f"📤 ارسال پارت {idx} از {len(result)}..."
                                )
                            with open(file_path, "rb") as vid:
                                await context.bot.send_video(
                                    chat_id=chat_id,
                                    video=vid,
                                    read_timeout=300,
                                    write_timeout=300,
                                    connect_timeout=60,
                                )
                        await update.message.reply_text("✅ ارسال با موفقیت انجام شد!")
                    except Exception as send_err:
                        print(f"❌ Send error: {send_err}")
                        await update.message.reply_text(
                            f"❌ خطا در ارسال: {str(send_err)}"
                        )
                    finally:
                        # حذف امن تمام فایل‌های ساخته شده
                        for file_path in result:
                            if os.path.exists(file_path):
                                os.remove(file_path)
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

    # توجه: در کد اصلی شما دو بلاک elif step == "waiting_yt_link" وجود داشت که آنها را یکی کردیم
    elif step == "waiting_yt_link":
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        dl_format = state_data.get("format")

        # اگر در مرحله انتخاب فرمت نیستیم و لینک داده شده است
        if not dl_format:
            set_state(chat_id, "waiting_yt_format", yt_url=text)
            await update.message.reply_text(
                "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        # اگر در مرحله‌ای هستیم که فرمت قبلا در state هست (بلاک دوم کد شما)
        if dl_format == "video":
            await update.message.reply_text("⏳ در حال دانلود ویدیو...")
            result = await asyncio.to_thread(download_youtube_video, text)

            if result == "TOO_LARGE":
                await update.message.reply_text(
                    "⚠️ حجم این ویدیو بیشتر از ۳۰۰ مگابایته و امکان ارسال نداره.\n"
                    "لطفاً ویدیوی کم‌حجم‌تری انتخاب کن."
                )
            elif isinstance(result, list) and len(result) > 0:
                try:
                    for idx, file_path in enumerate(result, 1):
                        if len(result) > 1:
                            await update.message.reply_text(
                                f"📤 ارسال پارت {idx} از {len(result)}..."
                            )
                        with open(file_path, "rb") as vid:
                            await context.bot.send_video(
                                chat_id=chat_id,
                                video=vid,
                                read_timeout=300,
                                write_timeout=300,
                            )
                finally:
                    for file_path in result:
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

    elif step == "waiting_yt_format":
        url = state_data.get("yt_url")
        if text == BTN_YT_VIDEO:
            await update.message.reply_text(
                "⏳ در حال بررسی و دانلود ویدیو (ممکن است زمان‌بر باشد)..."
            )
            result = await asyncio.to_thread(download_youtube_video, url)

            if result == "TOO_LARGE":
                await update.message.reply_text(
                    "⚠️ حجم این ویدیو بیشتر از ۳۰۰ مگابایته و امکان ارسال نداره.\n"
                    "لطفاً ویدیوی کم‌حجم‌تری انتخاب کن."
                )
            elif isinstance(result, list) and len(result) > 0:
                try:
                    for idx, file_path in enumerate(result, 1):
                        if len(result) > 1:
                            await update.message.reply_text(
                                f"📤 ارسال پارت {idx} از {len(result)}..."
                            )
                        with open(file_path, "rb") as vid:
                            await context.bot.send_video(
                                chat_id=chat_id,
                                video=vid,
                                read_timeout=300,
                                write_timeout=300,
                                connect_timeout=60,
                            )
                finally:
                    for file_path in result:
                        if os.path.exists(file_path):
                            os.remove(file_path)
            else:
                await update.message.reply_text("❌ دانلود شکست خورد.")
            return
