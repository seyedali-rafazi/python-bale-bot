# handlers/states/state_youtube.py

import os
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import BTN_YT_VIDEO, BTN_YT_AUDIO, BTN_BACK
from core.keyboards import get_yt_format_keyboard
from services.youtube import (
    download_youtube_video,
    download_youtube_audio,
    search_yt_videos,
)

# متغیر سراسری برای شمارش افراد در صف
active_downloads = 0
# محدودکننده دانلودهای همزمان به 2 عدد
MAX_CONCURRENT_DOWNLOADS = 2
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


async def background_yt_download(
    context: ContextTypes.DEFAULT_TYPE, url: str, chat_id: str, format_type: str
):
    global active_downloads
    active_downloads += 1
    queue_pos = active_downloads

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ درخواست شما ثبت شد.\nشما نفر {queue_pos} در کل صف (در حال انجام + منتظر) هستید.\nلطفاً تا خالی شدن ظرفیت منتظر بمانید...",
    )

    try:
        # منتظر ماندن در صف تا زمانی که نوبت کاربر برسد (حداکثر 2 پردازش همزمان)
        async with download_semaphore:
            progress_dict = {"text": "شروع پردازش...", "is_finished": False}

            async def update_progress_message():
                last_text = ""
                while not progress_dict.get("is_finished", False):
                    current_text = progress_dict.get("text", "")
                    if current_text and current_text != last_text:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg.message_id,
                                text=f"⏳ نوبت شما رسید! در حال پردازش...\n\n{current_text}",
                            )
                            last_text = current_text
                        except Exception:
                            pass
                    await asyncio.sleep(
                        3
                    )  # آپدیت هر 3 ثانیه برای جلوگیری از لیمیت شدن تلگرام

            updater_task = asyncio.create_task(update_progress_message())

            try:
                if format_type == "video":
                    result = await asyncio.to_thread(
                        download_youtube_video, url, progress_dict
                    )
                    progress_dict["is_finished"] = True

                    if result == "TOO_LARGE":
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="⚠️ حجم این ویدیو بیشتر از ۳۰۰ مگابایته و امکان پردازش نداره.\nلطفاً ویدیوی کم‌حجم‌تری انتخاب کن.",
                        )
                    elif isinstance(result, list) and len(result) > 0:
                        try:
                            part_msg = (
                                f" (شامل {len(result)} پارت به دلیل حجم بالا)"
                                if len(result) > 1
                                else ""
                            )
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"📤 در حال آپلود ویدیو{part_msg}...",
                            )

                            for idx, file_path in enumerate(result, 1):
                                if len(result) > 1:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"📤 ارسال پارت {idx} از {len(result)}...",
                                    )
                                with open(file_path, "rb") as vid:
                                    await context.bot.send_video(
                                        chat_id=chat_id,
                                        video=vid,
                                        read_timeout=300,
                                        write_timeout=300,
                                        connect_timeout=60,
                                    )
                            await context.bot.send_message(
                                chat_id=chat_id, text="✅ ارسال با موفقیت انجام شد!"
                            )
                        except Exception as send_err:
                            print(f"❌ Send error: {send_err}")
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"❌ خطا در ارسال: {str(send_err)}",
                            )
                        finally:
                            for file_path in result:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="❌ دانلود شکست خورد یا فایل پیدا نشد.",
                        )

                elif format_type == "audio":
                    file_path, title, perf = await asyncio.to_thread(
                        download_youtube_audio, url, progress_dict
                    )
                    progress_dict["is_finished"] = True

                    if file_path and os.path.exists(file_path):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id, text="📤 در حال آپلود فایل صوتی..."
                            )
                            with open(file_path, "rb") as aud:
                                await context.bot.send_audio(
                                    chat_id=chat_id,
                                    audio=aud,
                                    title=title,
                                    performer=perf,
                                    read_timeout=300,
                                    write_timeout=300,
                                    connect_timeout=60,
                                )
                        finally:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id, text="❌ دانلود شکست خورد."
                        )

            except Exception as e:
                print(f"❌ Error in background task: {e}")
                progress_dict["is_finished"] = True
                await context.bot.send_message(
                    chat_id=chat_id, text=f"❌ خطا: {str(e)}"
                )

            finally:
                progress_dict["is_finished"] = True
                updater_task.cancel()

    finally:
        active_downloads -= 1


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
        await update.message.reply_text("⏳ در حال جستجو در کانال...")
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

                asyncio.create_task(
                    background_yt_download(
                        context, selected_video["url"], chat_id, "video"
                    )
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

        dl_format = state_data.get("format")

        if not dl_format:
            set_state(chat_id, "waiting_yt_format", yt_url=text)
            await update.message.reply_text(
                "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        if dl_format == "video":
            asyncio.create_task(background_yt_download(context, text, chat_id, "video"))
        elif dl_format == "audio":
            asyncio.create_task(background_yt_download(context, text, chat_id, "audio"))

        return

    elif step == "waiting_yt_format":
        url = state_data.get("yt_url")

        if text == BTN_YT_VIDEO:
            asyncio.create_task(background_yt_download(context, url, chat_id, "video"))
            return

        elif text == BTN_YT_AUDIO:
            asyncio.create_task(background_yt_download(context, url, chat_id, "audio"))
            return
