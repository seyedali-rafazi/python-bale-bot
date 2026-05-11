# handlers/states/state_youtube.py

import os
import asyncio
import re
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from core.state_manager import set_state, get_state, clear_state
from core.constants import BTN_YT_VIDEO, BTN_BACK
from core.keyboards import get_yt_format_keyboard, get_main_menu_keyboard
from core.database import (
    is_vip,
    get_yt_downloads,
    increment_yt_downloads,
    decrement_yt_downloads,
    get_cached_video,
    save_cached_video,
    increment_yt_video_view,
)
from services.youtube import (
    get_video_precheck,
    download_youtube_video,
    download_youtube_audio,
    search_yt_videos,
    split_video_if_needed,
)
from services.telegram_backup import download_from_telegram_bot

try:
    from services.parspack_s3 import upload_to_s3
except ImportError:
    upload_to_s3 = None


MAX_NORMAL_DOWNLOADS = 1
MAX_VIP_DOWNLOADS = 4

normal_semaphore = asyncio.Semaphore(MAX_NORMAL_DOWNLOADS)
vip_semaphore = asyncio.Semaphore(MAX_VIP_DOWNLOADS)

STORAGE_CHANNEL_ID = "@digiacharstorage"


# -------------------- Helpers -------------------- #


async def check_user_limit(chat_id: str) -> bool:
    vip_status = await asyncio.to_thread(is_vip, chat_id)
    limit = 18 if vip_status else 1
    usage = await asyncio.to_thread(get_yt_downloads, chat_id)
    return usage < limit


def extract_yt_id(url: str):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else url


def get_waiting_count(semaphore: asyncio.Semaphore, max_concurrent: int) -> int:
    try:
        waiters = len(semaphore._waiters) if semaphore._waiters else 0
        running = max_concurrent - semaphore._value
        return max(0, running + waiters)
    except Exception:
        return 0


def is_non_backup_youtube_error(error_text: str) -> bool:
    error_text = (error_text or "").lower()

    blocked_keywords = [
        "too_large",
        "too large",
        "max-filesize",
        "auth_required",
        "sign in to confirm you're not a bot",
        "cookies",
        "private video",
        "video unavailable",
        "metadata_failed",
        "unknown_size",
        "could not detect video id",
        "failed to get video id",
        "download failed",
        "video_unavailable",
        "private_video",
    ]

    return any(keyword in error_text for keyword in blocked_keywords)


async def send_video_once(context, chat_id: str, file_id: str):
    try:
        await context.bot.send_video(chat_id=chat_id, video=file_id)
        return True
    except Exception as e:
        print(f"⚠️ Error sending video file_id to user {chat_id}: {e}")
        return False


async def send_audio_once(context, chat_id: str, file_id: str):
    try:
        await context.bot.send_audio(chat_id=chat_id, audio=file_id)
        return True
    except Exception as e:
        print(f"⚠️ Error sending audio file_id to user {chat_id}: {e}")
        return False


async def upload_video_to_storage_once(context, file_path: str, caption: str):
    with open(file_path, "rb") as vid:
        channel_msg = await context.bot.send_video(
            chat_id=STORAGE_CHANNEL_ID,
            video=vid,
            caption=caption,
            read_timeout=120,
            write_timeout=120,
            connect_timeout=30,
            pool_timeout=30,
        )
    return channel_msg.video.file_id


async def upload_audio_to_storage_once(context, file_path: str, caption: str):
    with open(file_path, "rb") as aud:
        channel_msg = await context.bot.send_audio(
            chat_id=STORAGE_CHANNEL_ID,
            audio=aud,
            title="صوت یوتیوب",
            performer="ربات دانلودر",
            caption=caption,
            read_timeout=120,
            write_timeout=120,
            connect_timeout=30,
            pool_timeout=30,
        )
    return channel_msg.audio.file_id


async def process_and_send_video_parts(
    context,
    chat_id: str,
    result_files: list,
    video_id: str,
    cache_key: str,
):
    uploaded_file_ids = []
    total_parts = len(result_files)
    part_msg = f" (شامل {total_parts} پارت)" if total_parts > 1 else ""

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📤 در حال آپلود ویدیو{part_msg}...",
    )

    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📤 آپلود پارت {idx} از {total_parts}...",
            )

        caption = f"Video ID: {video_id} | Part {idx}/{total_parts}"

        try:
            current_file_id = await upload_video_to_storage_once(
                context=context,
                file_path=file_path,
                caption=caption,
            )

            send_success = await send_video_once(context, chat_id, current_file_id)
            if not send_success:
                raise Exception("خطا در فوروارد/ارسال به کاربر")

            uploaded_file_ids.append(current_file_id)

        except Exception as e:
            print(f"❌ Error uploading/sending part {idx}: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ متاسفانه در آپلود یا ارسال پارت {idx} مشکلی پیش آمد. عملیات لغو شد.",
            )
            raise e

        await asyncio.sleep(1)

    if len(uploaded_file_ids) == total_parts:
        await asyncio.to_thread(save_cached_video, cache_key, uploaded_file_ids)
        await context.bot.send_message(chat_id=chat_id, text="✅ پایان عملیات ارسال.")


async def process_and_send_backup_video_parts(
    context,
    chat_id: str,
    result_files: list,
    video_id: str,
    cache_key: str,
):
    uploaded_file_ids = []
    total_parts = len(result_files)

    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📤 ارسال پارت بکاپ {idx} از {total_parts}...",
            )

        caption = f"Video ID: {video_id} (Backup) | Part {idx}/{total_parts}"

        try:
            current_file_id = await upload_video_to_storage_once(
                context=context,
                file_path=file_path,
                caption=caption,
            )

            send_success = await send_video_once(context, chat_id, current_file_id)
            if not send_success:
                raise Exception("خطا در ارسال پارت بکاپ")

            uploaded_file_ids.append(current_file_id)

        except Exception as e:
            print(f"❌ Error backup part {idx}: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ ارسال پارت {idx} ناموفق بود. عملیات بکاپ لغو شد.",
            )
            raise e

        await asyncio.sleep(1)

    if len(uploaded_file_ids) == total_parts:
        await asyncio.to_thread(save_cached_video, cache_key, uploaded_file_ids)
        await context.bot.send_message(
            chat_id=chat_id, text="✅ پایان عملیات ارسال بکاپ."
        )


async def send_cached_files(
    context, chat_id: str, cached_files: list, format_type: str
):
    await context.bot.send_message(
        chat_id=chat_id,
        text="✅ این فایل در سرور موجود است. در حال ارسال فوری...",
    )

    total_parts = len(cached_files)
    for idx, file_id in enumerate(cached_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📤 ارسال پارت {idx} از {total_parts}...",
            )

        if format_type == "video":
            await send_video_once(context, chat_id, file_id)
        else:
            await send_audio_once(context, chat_id, file_id)

        await asyncio.sleep(1)


# -------------------- Main Background Task -------------------- #


async def background_yt_download(
    context, url: str, chat_id: str, format_type: str, destination: str = "telegram"
):
    video_id = extract_yt_id(url)
    cache_key = f"{video_id}_{format_type}_{destination}"

    if destination == "telegram":
        cached_files = await asyncio.to_thread(get_cached_video, cache_key)
        if cached_files:
            await send_cached_files(context, chat_id, cached_files, format_type)
            await asyncio.to_thread(increment_yt_video_view, cache_key)
            return

    precheck = None

    # ✅ one-request precheck فقط برای video
    if format_type == "video":
        precheck = await asyncio.to_thread(get_video_precheck, url)

        if not precheck.get("ok"):
            reason = precheck.get("reason", "UNKNOWN")
            print(f"❌ YouTube precheck failed: {precheck}")

            if reason == "AUTH_REQUIRED":
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ یوتیوب اجازه دریافت اطلاعات این ویدیو را نداد (نیاز به کوکی/احراز هویت).",
                )
            elif reason == "VIDEO_UNAVAILABLE":
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ این ویدیو در دسترس نیست.",
                )
            elif reason == "PRIVATE_VIDEO":
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ این ویدیو خصوصی است.",
                )
            elif reason == "UNKNOWN_SIZE":
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ حجم ویدیو قابل تشخیص نیست؛ برای جلوگیری از دانلود فایل حجیم، عملیات متوقف شد.",
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ دریافت اطلاعات ویدیو ناموفق بود. دانلود انجام نشد.",
                )

            await asyncio.to_thread(decrement_yt_downloads, chat_id)
            return

        size = precheck.get("size")
        if size and size > 300 * 1024 * 1024:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ حجم ویدیو بیشتر از 300MB است.",
            )
            await asyncio.to_thread(decrement_yt_downloads, chat_id)
            return

        if precheck.get("thumbnail"):
            caption = (
                f"🎥 **{precheck.get('title', 'بدون عنوان')}**\n"
                f"👤 کانال: {precheck.get('uploader', 'نامشخص')}\n"
                f"⏱ زمان: {precheck.get('duration', 0)} ثانیه\n\n"
                f"⏳ در حال آماده‌سازی برای دانلود..."
            )
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=precheck["thumbnail"],
                    caption=caption,
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    user_is_vip = await asyncio.to_thread(is_vip, chat_id)
    active_semaphore = vip_semaphore if user_is_vip else normal_semaphore
    max_concurrent = MAX_VIP_DOWNLOADS if user_is_vip else MAX_NORMAL_DOWNLOADS

    waiting_count = get_waiting_count(active_semaphore, max_concurrent)

    if waiting_count > 0:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ درخواست شما ثبت شد.\nسرور شلوغ است. در صف قرار گرفتید...",
        )
    else:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ درخواست شما ثبت شد و پردازش آغاز گردید...",
        )

    try:
        async with active_semaphore:
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
                    await asyncio.sleep(5)

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
                                text="⚠️ حجم ویدیو بیشتر از حد مجاز است.",
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)
                            return

                        elif raw_file == "AUTH_REQUIRED":
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ یوتیوب برای این ویدیو احراز هویت/کوکی می‌خواهد. دانلود انجام نشد.",
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)
                            return

                        elif raw_file == "VIDEO_UNAVAILABLE":
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ این ویدیو در دسترس نیست.",
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)
                            return

                        elif raw_file == "PRIVATE_VIDEO":
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ این ویدیو خصوصی است.",
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)
                            return

                        elif raw_file in ["METADATA_FAILED", "DOWNLOAD_FAILED", None]:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ دانلود از یوتیوب ناموفق بود. بکاپ اجرا نشد.",
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)
                            return

                        elif raw_file and isinstance(raw_file, str):
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg.message_id,
                                text="⏳ در حال آماده‌سازی ویدیو...",
                            )

                            result = (
                                await split_video_if_needed(raw_file)
                                if destination == "telegram"
                                else [raw_file]
                            )
                            downloaded_files.extend(result)

                            if destination == "server":
                                await context.bot.send_message(
                                    chat_id=chat_id, text="☁️ آپلود در فضای ابری ..."
                                )

                                progress_dict["is_finished"] = False
                                progress_dict["text"] = "☁️ شروع آپلود ابری..."
                                updater_task = asyncio.create_task(
                                    update_progress_message()
                                )

                                s3_links = []
                                for file_path in result:
                                    s3_url = await asyncio.to_thread(
                                        upload_to_s3, file_path, None, progress_dict
                                    )
                                    if s3_url:
                                        s3_links.append(s3_url)

                                progress_dict["is_finished"] = True

                                if s3_links:
                                    links_text = "\n\n".join(
                                        [
                                            f"🔗 [لینک دانلود فایل]({link})"
                                            for link in s3_links
                                        ]
                                    )
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"✅ فایل ذخیره شد:\n\n{links_text}",
                                        parse_mode="Markdown",
                                    )
                                else:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ خطا در آپلود به سرور ابری.",
                                    )
                                    await asyncio.to_thread(
                                        decrement_yt_downloads, chat_id
                                    )
                            else:
                                await process_and_send_video_parts(
                                    context, chat_id, result, video_id, cache_key
                                )

                        else:
                            raise Exception("DOWNLOAD_FAILED")

                    except Exception as send_err:
                        print(f"❌ Video error: {send_err}")
                        error_text = str(send_err).lower()

                        # ✅ خطاهای غیرقابل بکاپ
                        if is_non_backup_youtube_error(error_text):
                            if (
                                "too_large" in error_text
                                or "max-filesize" in error_text
                            ):
                                msg = "❌ حجم ویدیو بیشتر از حد مجاز (300MB) است."
                            elif (
                                "auth_required" in error_text
                                or "cookies" in error_text
                                or "not a bot" in error_text
                            ):
                                msg = "❌ یوتیوب درخواست احراز هویت/کوکی داده است. دانلود انجام نشد."
                            elif (
                                "private video" in error_text
                                or "private_video" in error_text
                            ):
                                msg = "❌ این ویدیو خصوصی است."
                            elif (
                                "video unavailable" in error_text
                                or "video_unavailable" in error_text
                            ):
                                msg = "❌ این ویدیو در دسترس نیست."
                            elif (
                                "unknown_size" in error_text
                                or "metadata_failed" in error_text
                            ):
                                msg = "❌ اطلاعات کافی برای دانلود امن این ویدیو دریافت نشد."
                            else:
                                msg = "❌ دانلود از یوتیوب ناموفق بود و بکاپ اجرا نشد."

                            await context.bot.send_message(chat_id=chat_id, text=msg)
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)
                            return

                        await context.bot.send_message(
                            chat_id=chat_id, text="⚠️ تلاش از طریق سرور بکاپ ... ⏳"
                        )

                        try:
                            backup_file = await download_from_telegram_bot(url)
                            if backup_file and os.path.exists(backup_file):
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="⏳ در حال آماده‌سازی فایل بکاپ...",
                                )

                                if destination == "server":
                                    progress_dict["is_finished"] = False
                                    progress_dict["text"] = "☁️ شروع آپلود فایل بکاپ..."
                                    updater_task = asyncio.create_task(
                                        update_progress_message()
                                    )

                                    s3_url = await asyncio.to_thread(
                                        upload_to_s3, backup_file, None, progress_dict
                                    )
                                    progress_dict["is_finished"] = True

                                    if s3_url:
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text=f"✅ ذخیره در ابری:\n\n🔗 [لینک]({s3_url})",
                                            parse_mode="Markdown",
                                        )
                                    else:
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text="❌ خطا در آپلود ابری.",
                                        )
                                        await asyncio.to_thread(
                                            decrement_yt_downloads, chat_id
                                        )
                                else:
                                    result = await split_video_if_needed(backup_file)
                                    downloaded_files.extend(result)
                                    await process_and_send_backup_video_parts(
                                        context, chat_id, result, video_id, cache_key
                                    )
                            else:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ سرور بکاپ ناموفق بود.",
                                )
                                await asyncio.to_thread(decrement_yt_downloads, chat_id)

                        except Exception as backup_err:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"❌ خطای بکاپ: {str(backup_err)}",
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)

                    finally:
                        for file_path in downloaded_files:
                            if os.path.exists(file_path):
                                try:
                                    await asyncio.to_thread(os.remove, file_path)
                                except Exception:
                                    pass

                elif format_type == "audio":
                    file_path = None
                    try:
                        file_path = await asyncio.to_thread(
                            download_youtube_audio, url, progress_dict
                        )
                        progress_dict["is_finished"] = True

                        if (
                            file_path
                            and isinstance(file_path, str)
                            and os.path.exists(file_path)
                        ):
                            if destination == "server":
                                await context.bot.send_message(
                                    chat_id=chat_id, text="☁️ آپلود در سرور ابری..."
                                )
                                progress_dict["is_finished"] = False
                                progress_dict["text"] = "☁️ شروع آپلود ابری..."
                                updater_task = asyncio.create_task(
                                    update_progress_message()
                                )

                                s3_url = await asyncio.to_thread(
                                    upload_to_s3, file_path, None, progress_dict
                                )
                                progress_dict["is_finished"] = True

                                if s3_url:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"✅ ذخیره شد:\n\n🔗 [لینک]({s3_url})",
                                        parse_mode="Markdown",
                                    )
                                else:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ خطا در آپلود ابری.",
                                    )
                                    await asyncio.to_thread(
                                        decrement_yt_downloads, chat_id
                                    )
                            else:
                                await context.bot.send_message(
                                    chat_id=chat_id, text="📤 آپلود فایل صوتی..."
                                )
                                try:
                                    file_id = await upload_audio_to_storage_once(
                                        context, file_path, f"Audio ID: {video_id}"
                                    )
                                    await send_audio_once(context, chat_id, file_id)
                                    await asyncio.to_thread(
                                        save_cached_video, cache_key, [file_id]
                                    )
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="✅ ارسال با موفقیت انجام شد!",
                                    )
                                except Exception:
                                    await context.bot.send_message(
                                        chat_id=chat_id, text="❌ خطا در ارسال صوت."
                                    )
                        else:
                            await context.bot.send_message(
                                chat_id=chat_id, text="❌ دانلود شکست خورد."
                            )
                            await asyncio.to_thread(decrement_yt_downloads, chat_id)

                    except Exception as send_err:
                        await context.bot.send_message(
                            chat_id=chat_id, text=f"❌ خطا: {str(send_err)}"
                        )
                        await asyncio.to_thread(decrement_yt_downloads, chat_id)
                    finally:
                        if file_path and os.path.exists(file_path):
                            try:
                                await asyncio.to_thread(os.remove, file_path)
                            except Exception:
                                pass

            except Exception as e:
                progress_dict["is_finished"] = True
                await context.bot.send_message(
                    chat_id=chat_id, text=f"❌ خطا: {str(e)}"
                )
                await asyncio.to_thread(decrement_yt_downloads, chat_id)
            finally:
                progress_dict["is_finished"] = True
                updater_task.cancel()

    except Exception as e:
        print(f"Semaphore Error: {e}")
        await asyncio.to_thread(decrement_yt_downloads, chat_id)


# -------------------- State Handler -------------------- #


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

        await asyncio.to_thread(
            set_state, chat_id, "waiting_yt_selection", videos=results
        )
        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
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

        await asyncio.to_thread(
            set_state, chat_id, "waiting_yt_selection", videos=results
        )
        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    elif step == "waiting_yt_ch_search_name":
        await asyncio.to_thread(
            set_state, chat_id, "waiting_yt_ch_search_query", channel=text
        )
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

        await asyncio.to_thread(
            set_state, chat_id, "waiting_yt_selection", videos=results
        )
        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    elif step == "waiting_yt_selection":
        if text.startswith("📥 دانلود ویدیو "):
            if not await check_user_limit(chat_id):
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

                await asyncio.to_thread(
                    set_state,
                    chat_id,
                    "waiting_yt_format",
                    yt_url=selected_video["url"],
                )
                await update.message.reply_text(
                    "✅ ویدیو انتخاب شد! فرمت را انتخاب کنید 👇",
                    reply_markup=get_yt_format_keyboard(),
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
            await asyncio.to_thread(
                set_state, chat_id, "waiting_yt_format", yt_url=text
            )
            await update.message.reply_text(
                "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        if not await check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        await asyncio.to_thread(
            set_state, chat_id, "waiting_yt_destination", yt_url=text, format=dl_format
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 آپلود مستقیم (بله)",
                        callback_data="ytdest_telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "☁️ آپلود در سرور ابری (ویژه Pro ⭐️)",
                        callback_data="ytdest_server",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=keyboard,
        )
        return

    elif step == "waiting_yt_format":
        url = state_data.get("yt_url")

        if not await check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        format_type = "video" if text == BTN_YT_VIDEO else "audio"

        await asyncio.to_thread(
            set_state, chat_id, "waiting_yt_destination", yt_url=url, format=format_type
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 آپلود مستقیم (بله)",
                        callback_data="ytdest_telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "☁️ آپلود در سرور ابری (ویژه Pro ⭐️)",
                        callback_data="ytdest_server",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=keyboard,
        )
        return


# -------------------- Callback -------------------- #


async def youtube_destination_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    data = query.data
    chat_id = str(query.message.chat_id)

    if data not in ["ytdest_telegram", "ytdest_server"]:
        return

    user_state = await asyncio.to_thread(get_state, chat_id)
    if not user_state or user_state.get("step") != "waiting_yt_destination":
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    url = user_state.get("yt_url")
    format_type = user_state.get("format")

    if data == "ytdest_server":
        if not await asyncio.to_thread(is_vip, chat_id):
            await query.edit_message_text(
                "❌ این قابلیت فقط مخصوص کاربران ویژه (Pro ⭐️) می‌باشد."
            )
            return
        destination = "server"
    else:
        destination = "telegram"

    await query.edit_message_text("✅ درخواست ثبت شد. در حال انتقال به صف دانلود...")

    await asyncio.to_thread(clear_state, chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔙 بازگشت به منوی اصلی",
        reply_markup=get_main_menu_keyboard(),
    )

    await asyncio.to_thread(increment_yt_downloads, chat_id)

    asyncio.create_task(
        background_yt_download(context, url, chat_id, format_type, destination)
    )
