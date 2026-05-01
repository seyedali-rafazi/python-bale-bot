# handlers/states/state_youtube.py

import os
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import BTN_YT_VIDEO, BTN_YT_AUDIO, BTN_BACK
from core.keyboards import get_yt_format_keyboard
from core.database import (
    is_vip,
    get_yt_downloads,
    increment_yt_downloads,
    get_cached_video,
    save_cached_video,
)

from services.youtube import (
    download_youtube_video,
    download_youtube_audio,
    search_yt_videos,
    split_video_if_needed,
)
from services.telegram_backup import download_from_telegram_bot
import re

MAX_CONCURRENT_DOWNLOADS = 3  # تعداد دانلودهای همزمان
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
STORAGE_CHANNEL_ID = "@digiacharstorage"  # کانال ارشیو


def check_user_limit(chat_id: str) -> bool:
    vip_status = is_vip(chat_id)
    limit = 20 if vip_status else 2
    usage = get_yt_downloads(chat_id)
    return usage < limit


def extract_yt_id(url: str):
    """استخراج سریع آیدی ویدیو از لینک یوتیوب برای ساخت کلید کش"""
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else url


async def background_yt_download(context, url: str, chat_id: str, format_type: str):
    video_id = extract_yt_id(url)
    cache_key = f"{video_id}_{format_type}"

    # ------------------ 1. بررسی کش (Cache) ------------------
    cached_files = get_cached_video(cache_key)
    if cached_files:
        await context.bot.send_message(
            chat_id=chat_id, text="✅ این فایل در سرور موجود است. در حال ارسال فوری..."
        )
        for idx, file_id in enumerate(cached_files, 1):
            if len(cached_files) > 1:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📤 ارسال پارت {idx} از {len(cached_files)}...",
                )
            try:
                if format_type == "video":
                    await context.bot.send_video(chat_id=chat_id, video=file_id)
                else:
                    await context.bot.send_audio(chat_id=chat_id, audio=file_id)
            except Exception as e:
                print(f"❌ Error sending cached file {file_id}: {e}")

        increment_yt_downloads(chat_id)
        return
    # ---------------------------------------------------------

    # بررسی وضعیت صف با استفاده از سمفور
    waiting_count = max(
        0,
        MAX_CONCURRENT_DOWNLOADS
        - download_semaphore._value
        + len(download_semaphore._waiters)
        if download_semaphore._waiters
        else 0,
    )

    if waiting_count > 0:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ درخواست شما ثبت شد.\nسرور در حال حاضر شلوغ است. در صف قرار گرفتید...\nلطفاً منتظر بمانید.",
        )
    else:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ درخواست شما ثبت شد و پردازش آغاز گردید...",
        )

    try:
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
                                text=f"⏳ در حال پردازش...\n\n{current_text}",
                            )
                            last_text = current_text
                        except Exception:
                            pass
                    await asyncio.sleep(8)

            updater_task = asyncio.create_task(update_progress_message())

            try:
                if format_type == "video":
                    downloaded_files = []
                    try:
                        raw_file = await asyncio.to_thread(
                            download_youtube_video, url, progress_dict
                        )
                        progress_dict["is_finished"] = True

                        if raw_file == "TOO_LARGE":
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="⚠️ حجم این ویدیو بیشتر از ۳۰۰ مگابایته و امکان پردازش نداره.",
                            )
                        elif raw_file and isinstance(raw_file, str):
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg.message_id,
                                text="⏳ در حال آماده‌سازی و برش ویدیو...",
                            )
                            result = await split_video_if_needed(raw_file)
                            downloaded_files.extend(result)

                            part_msg = (
                                f" (شامل {len(result)} پارت به دلیل حجم بالا)"
                                if len(result) > 1
                                else ""
                            )

                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"📤 در حال آپلود ویدیو در سرور{part_msg}...",
                            )

                            uploaded_file_ids = []
                            for idx, file_path in enumerate(result, 1):
                                if len(result) > 1:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"📤 ارسال پارت {idx} از {len(result)}...",
                                    )
                                with open(file_path, "rb") as vid:
                                    # 1. ارسال به کانال آرشیو
                                    channel_msg = await context.bot.send_video(
                                        chat_id=STORAGE_CHANNEL_ID,
                                        video=vid,
                                        caption=f"Video ID: {video_id} | Part {idx}/{len(result)}",
                                        read_timeout=300,
                                        write_timeout=300,
                                        connect_timeout=60,
                                    )
                                    file_id = channel_msg.video.file_id
                                    uploaded_file_ids.append(file_id)

                                    # 2. ارسال به کاربر با استفاده از file_id
                                    await context.bot.send_video(
                                        chat_id=chat_id, video=file_id
                                    )

                            # 3. ذخیره در کش
                            if uploaded_file_ids:
                                save_cached_video(cache_key, uploaded_file_ids)

                            await context.bot.send_message(
                                chat_id=chat_id, text="✅ ارسال با موفقیت انجام شد!"
                            )
                            increment_yt_downloads(chat_id)

                        else:
                            raise Exception(
                                "yt-dlp returned None (YouTube bot block or download failed)"
                            )

                    except Exception as send_err:
                        print(f"❌ Video process error: {send_err}")
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="⚠️ دانلود مستقیم با مشکل مواجه شد. در حال تلاش از طریق سرور بکاپ ... ⏳",
                        )

                        try:
                            # استفاده از بکاپ تلثون
                            backup_file = await download_from_telegram_bot(url)

                            if backup_file and os.path.exists(backup_file):
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="⏳ فایل از سرور بکاپ دریافت شد، در حال آماده‌سازی...",
                                )

                                result = await split_video_if_needed(backup_file)
                                downloaded_files.extend(result)

                                uploaded_file_ids = []
                                for idx, file_path in enumerate(result, 1):
                                    if len(result) > 1:
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text=f"📤 ارسال پارت {idx} از {len(result)}...",
                                        )
                                    with open(file_path, "rb") as vid:
                                        # ارسال به کانال آرشیو
                                        channel_msg = await context.bot.send_video(
                                            chat_id=STORAGE_CHANNEL_ID,
                                            video=vid,
                                            caption=f"Video ID: {video_id} (Backup) | Part {idx}/{len(result)}",
                                            read_timeout=300,
                                            write_timeout=300,
                                            connect_timeout=60,
                                        )
                                        file_id = channel_msg.video.file_id
                                        uploaded_file_ids.append(file_id)

                                        # ارسال به کاربر
                                        await context.bot.send_video(
                                            chat_id=chat_id, video=file_id
                                        )

                                if uploaded_file_ids:
                                    save_cached_video(cache_key, uploaded_file_ids)

                                increment_yt_downloads(chat_id)
                                await context.bot.send_message(
                                    chat_id=chat_id, text="✅ ارسال با موفقیت انجام شد!"
                                )
                            else:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ سرور بکاپ هم نتوانست ویدیو را دانلود کند.",
                                )
                        except Exception as backup_err:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"❌ خطای سرور بکاپ: {str(backup_err)}",
                            )

                    finally:
                        for file_path in downloaded_files:
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except Exception as e:
                                    print(f"❌ Cleanup error (video): {e}")

                elif format_type == "audio":
                    file_path = None
                    try:
                        file_path = await asyncio.to_thread(download_youtube_audio, url)
                        progress_dict["is_finished"] = True

                        if (
                            file_path
                            and isinstance(file_path, str)
                            and os.path.exists(file_path)
                        ):
                            await context.bot.send_message(
                                chat_id=chat_id, text="📤 در حال آپلود فایل صوتی..."
                            )

                            with open(file_path, "rb") as aud:
                                # 1. ارسال به کانال آرشیو
                                channel_msg = await context.bot.send_audio(
                                    chat_id=STORAGE_CHANNEL_ID,
                                    audio=aud,
                                    title="صوت یوتیوب",
                                    performer="ربات دانلودر",
                                    caption=f"Audio ID: {video_id}",
                                    read_timeout=300,
                                    write_timeout=300,
                                    connect_timeout=60,
                                )
                                file_id = channel_msg.audio.file_id

                                # 2. ارسال به کاربر
                                await context.bot.send_audio(
                                    chat_id=chat_id, audio=file_id
                                )

                                # 3. ذخیره در کش
                                save_cached_video(cache_key, [file_id])

                            increment_yt_downloads(chat_id)
                        else:
                            await context.bot.send_message(
                                chat_id=chat_id, text="❌ دانلود شکست خورد."
                            )
                    except Exception as send_err:
                        print(f"❌ Audio process error: {send_err}")
                        await context.bot.send_message(
                            chat_id=chat_id, text=f"❌ خطا: {str(send_err)}"
                        )
                    finally:
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception as e:
                                print(f"❌ Cleanup error (audio): {e}")

            except Exception as e:
                print(f"❌ Error in background task: {e}")
                progress_dict["is_finished"] = True
                await context.bot.send_message(
                    chat_id=chat_id, text=f"❌ خطا: {str(e)}"
                )

            finally:
                progress_dict["is_finished"] = True
                updater_task.cancel()

    except Exception as e:
        print(f"Semaphore Error: {e}")


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
            if not check_user_limit(chat_id):
                await update.message.reply_text(
                    "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
                )
                return

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

        if not check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        if dl_format == "video":
            asyncio.create_task(background_yt_download(context, text, chat_id, "video"))
        elif dl_format == "audio":
            asyncio.create_task(background_yt_download(context, text, chat_id, "audio"))

        return

    elif step == "waiting_yt_format":
        url = state_data.get("yt_url")

        if not check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        if text == BTN_YT_VIDEO:
            asyncio.create_task(background_yt_download(context, url, chat_id, "video"))
            return

        elif text == BTN_YT_AUDIO:
            asyncio.create_task(background_yt_download(context, url, chat_id, "audio"))
            return
