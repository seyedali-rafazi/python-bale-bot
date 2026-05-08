# handlers/states/state_youtube.py

import os
import asyncio
import re
import contextlib

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
from telegram.error import TimedOut

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


MAX_NORMAL_DOWNLOADS = 2
MAX_VIP_DOWNLOADS = 4

yt_normal_queue = asyncio.Queue()
yt_vip_queue = asyncio.Queue()
_workers_started = False

STORAGE_CHANNEL_ID = "@digiacharstorage"


# -------------------- Helpers -------------------- #


def check_user_limit(chat_id: str) -> bool:
    vip_status = is_vip(chat_id)
    limit = 18 if vip_status else 1
    usage = get_yt_downloads(chat_id)
    return usage < limit


def extract_yt_id(url: str):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else url


async def safe_send_message(context, chat_id: str, text: str, **kwargs):
    try:
        return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except TimedOut as e:
        print(f"⚠️ Timeout sending message to {chat_id}: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Error sending message to {chat_id}: {e}")
        return None


async def send_video_once(context, chat_id: str, file_id: str):
    """
    خروجی:
    success => ارسال موفق
    timeout => تایم‌اوت؛ ممکن است فایل ارسال شده باشد ولی پاسخ نگرفته‌ایم
    error   => خطای واقعی
    """
    try:
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            read_timeout=120,
            write_timeout=120,
            connect_timeout=30,
            pool_timeout=30,
        )
        return "success"
    except TimedOut as e:
        print(f"⚠️ Timeout sending video file_id to user {chat_id}: {e}")
        return "timeout"
    except Exception as e:
        print(f"⚠️ Error sending video file_id to user {chat_id}: {e}")
        return "error"


async def send_audio_once(context, chat_id: str, file_id: str):
    """
    خروجی:
    success => ارسال موفق
    timeout => تایم‌اوت؛ ممکن است فایل ارسال شده باشد ولی پاسخ نگرفته‌ایم
    error   => خطای واقعی
    """
    try:
        await context.bot.send_audio(
            chat_id=chat_id,
            audio=file_id,
            read_timeout=120,
            write_timeout=120,
            connect_timeout=30,
            pool_timeout=30,
        )
        return "success"
    except TimedOut as e:
        print(f"⚠️ Timeout sending audio file_id to user {chat_id}: {e}")
        return "timeout"
    except Exception as e:
        print(f"⚠️ Error sending audio file_id to user {chat_id}: {e}")
        return "error"


async def upload_video_to_storage_once(context, file_path: str, caption: str):
    """
    اگر اینجا TimedOut بخورد، یعنی ممکن است فایل در کانال آپلود شده باشد
    اما چون پاسخ نگرفتیم file_id نداریم؛ پس نباید cache کنیم.
    """
    with open(file_path, "rb") as vid:
        channel_msg = await context.bot.send_video(
            chat_id=STORAGE_CHANNEL_ID,
            video=vid,
            caption=caption,
            read_timeout=300,
            write_timeout=300,
            connect_timeout=60,
            pool_timeout=60,
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
            read_timeout=300,
            write_timeout=300,
            connect_timeout=60,
            pool_timeout=60,
        )
    return channel_msg.audio.file_id


async def process_and_send_video_parts(
    context, chat_id: str, result_files: list, video_id: str, cache_key: str
):
    uploaded_file_ids = []
    total_parts = len(result_files)
    part_msg = f" شامل {total_parts} پارت" if total_parts > 1 else ""
    has_timeout = False

    await safe_send_message(
        context,
        chat_id,
        f"📤 در حال آپلود ویدیو{part_msg}...",
    )

    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await safe_send_message(
                context,
                chat_id,
                f"📤 آپلود پارت {idx} از {total_parts}...",
            )

        caption = f"Video ID: {video_id} | Part {idx}/{total_parts}"

        try:
            current_file_id = await upload_video_to_storage_once(
                context=context,
                file_path=file_path,
                caption=caption,
            )

            send_status = await send_video_once(context, chat_id, current_file_id)

            if send_status == "success":
                uploaded_file_ids.append(current_file_id)

            elif send_status == "timeout":
                has_timeout = True
                await safe_send_message(
                    context,
                    chat_id,
                    f"⚠️ پارت {idx} احتمالاً ارسال شده، اما پاسخ تایید دریافت نشد. ادامه می‌دهم...",
                )

            else:
                raise Exception("خطا در ارسال ویدیو به کاربر")

        except TimedOut as e:
            print(f"⚠️ Timeout uploading part {idx}: {e}")
            has_timeout = True
            await safe_send_message(
                context,
                chat_id,
                f"⚠️ پارت {idx} هنگام آپلود دچار تایم‌اوت شد. ممکن است ارسال شده باشد. ادامه عملیات...",
            )

        except Exception as e:
            print(f"❌ Error uploading/sending part {idx}: {e}")
            await safe_send_message(
                context,
                chat_id,
                f"❌ متاسفانه در آپلود یا ارسال پارت {idx} مشکلی پیش آمد. عملیات لغو شد.",
            )
            raise

        await asyncio.sleep(1)

    if len(uploaded_file_ids) == total_parts and not has_timeout:
        save_cached_video(cache_key, uploaded_file_ids)
        await safe_send_message(
            chat_id=chat_id, context=context, text="✅ پایان عملیات ارسال."
        )
    else:
        await safe_send_message(
            context,
            chat_id,
            "⚠️ عملیات پایان یافت، اما چون در یک یا چند پارت تایم‌اوت رخ داد، فایل در دیتابیس ذخیره نشد.",
        )


async def process_and_send_backup_video_parts(
    context, chat_id: str, result_files: list, video_id: str, cache_key: str
):
    uploaded_file_ids = []
    total_parts = len(result_files)
    has_timeout = False

    await safe_send_message(
        context,
        chat_id,
        "📤 در حال ارسال فایل از سرور بکاپ...",
    )

    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await safe_send_message(
                context,
                chat_id,
                f"📤 ارسال پارت بکاپ {idx} از {total_parts}...",
            )

        caption = f"Video ID: {video_id} Backup | Part {idx}/{total_parts}"

        try:
            current_file_id = await upload_video_to_storage_once(
                context=context,
                file_path=file_path,
                caption=caption,
            )

            send_status = await send_video_once(context, chat_id, current_file_id)

            if send_status == "success":
                uploaded_file_ids.append(current_file_id)

            elif send_status == "timeout":
                has_timeout = True
                await safe_send_message(
                    context,
                    chat_id,
                    f"⚠️ پارت بکاپ {idx} احتمالاً ارسال شده، اما پاسخ تایید دریافت نشد. ادامه می‌دهم...",
                )

            else:
                raise Exception("خطا در ارسال پارت بکاپ به کاربر")

        except TimedOut as e:
            print(f"⚠️ Timeout backup part {idx}: {e}")
            has_timeout = True
            await safe_send_message(
                context,
                chat_id,
                f"⚠️ پارت بکاپ {idx} هنگام آپلود دچار تایم‌اوت شد. ادامه عملیات...",
            )

        except Exception as e:
            print(f"❌ Error backup part {idx}: {e}")
            await safe_send_message(
                context,
                chat_id,
                f"❌ ارسال پارت بکاپ {idx} ناموفق بود. عملیات بکاپ لغو شد.",
            )
            raise

        await asyncio.sleep(1)

    if len(uploaded_file_ids) == total_parts and not has_timeout:
        save_cached_video(cache_key, uploaded_file_ids)
        await safe_send_message(context, chat_id, "✅ پایان عملیات ارسال بکاپ.")
    else:
        await safe_send_message(
            context,
            chat_id,
            "⚠️ عملیات بکاپ پایان یافت، اما به دلیل تایم‌اوت در دیتابیس ذخیره نشد.",
        )


async def send_cached_files(
    context, chat_id: str, cached_files: list, format_type: str
):
    await safe_send_message(
        context,
        chat_id,
        "✅ این فایل در سرور موجود است. در حال ارسال فوری...",
    )

    total_parts = len(cached_files)

    for idx, file_id in enumerate(cached_files, 1):
        if total_parts > 1:
            await safe_send_message(
                context,
                chat_id,
                f"📤 ارسال پارت {idx} از {total_parts}...",
            )

        if format_type == "video":
            await send_video_once(context, chat_id, file_id)
        else:
            await send_audio_once(context, chat_id, file_id)

        await asyncio.sleep(1)


# -------------------- Worker System -------------------- #


async def execute_yt_download(
    context,
    url: str,
    chat_id: str,
    format_type: str,
    destination: str,
    status_msg,
):
    video_id = extract_yt_id(url)
    cache_key = f"{video_id}_{format_type}_{destination}"

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
                    download_youtube_video,
                    url,
                    progress_dict,
                )

                progress_dict["is_finished"] = True

                if raw_file == "TOO_LARGE":
                    await safe_send_message(
                        context,
                        chat_id,
                        "⚠️ حجم ویدیو بیشتر از حد مجاز است.",
                    )
                    decrement_yt_downloads(chat_id)
                    return

                elif raw_file and isinstance(raw_file, str):
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text="⏳ در حال آماده‌سازی ویدیو...",
                        )
                    except Exception:
                        pass

                    result = (
                        await split_video_if_needed(raw_file)
                        if destination == "telegram"
                        else [raw_file]
                    )

                    downloaded_files.extend(result)

                    if destination == "server":
                        if upload_to_s3 is None:
                            await safe_send_message(
                                context,
                                chat_id,
                                "❌ سرویس آپلود ابری در دسترس نیست.",
                            )
                            decrement_yt_downloads(chat_id)
                            return

                        await safe_send_message(
                            context,
                            chat_id,
                            "☁️ آپلود در فضای ابری ...",
                        )

                        s3_links = []

                        for file_path in result:
                            s3_url = await asyncio.to_thread(upload_to_s3, file_path)
                            if s3_url:
                                s3_links.append(s3_url)

                        if s3_links:
                            links_text = "\n\n".join(
                                [f"🔗 [لینک دانلود فایل]({link})" for link in s3_links]
                            )
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"✅ فایل ذخیره شد:\n\n{links_text}",
                                parse_mode="Markdown",
                            )
                        else:
                            await safe_send_message(
                                context,
                                chat_id,
                                "❌ خطا در آپلود به سرور ابری.",
                            )
                            decrement_yt_downloads(chat_id)

                    else:
                        await process_and_send_video_parts(
                            context,
                            chat_id,
                            result,
                            video_id,
                            cache_key,
                        )

                else:
                    raise Exception("Download failed")

            except Exception as send_err:
                print(f"❌ Video error: {send_err}")
                error_text = str(send_err).lower()

                if "too large" in error_text or "max-filesize" in error_text:
                    await safe_send_message(
                        context,
                        chat_id,
                        "⚠️ حجم ویدیو بیش از حد مجاز است.",
                    )
                    decrement_yt_downloads(chat_id)
                    return

                await safe_send_message(
                    context,
                    chat_id,
                    "⚠️ تلاش از طریق سرور بکاپ ... ⏳",
                )

                try:
                    backup_file = await download_from_telegram_bot(url)

                    if backup_file and os.path.exists(backup_file):
                        await safe_send_message(
                            context,
                            chat_id,
                            "⏳ در حال آماده‌سازی فایل بکاپ...",
                        )

                        if destination == "server":
                            if upload_to_s3 is None:
                                await safe_send_message(
                                    context,
                                    chat_id,
                                    "❌ سرویس آپلود ابری در دسترس نیست.",
                                )
                                decrement_yt_downloads(chat_id)
                                return

                            s3_url = await asyncio.to_thread(upload_to_s3, backup_file)

                            if s3_url:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=f"✅ ذخیره در ابری:\n\n🔗 [لینک]({s3_url})",
                                    parse_mode="Markdown",
                                )
                            else:
                                await safe_send_message(
                                    context,
                                    chat_id,
                                    "❌ خطا در آپلود ابری.",
                                )
                                decrement_yt_downloads(chat_id)

                        else:
                            result = await split_video_if_needed(backup_file)
                            downloaded_files.extend(result)

                            await process_and_send_backup_video_parts(
                                context,
                                chat_id,
                                result,
                                video_id,
                                cache_key,
                            )
                    else:
                        await safe_send_message(
                            context,
                            chat_id,
                            "❌ سرور بکاپ ناموفق بود.",
                        )
                        decrement_yt_downloads(chat_id)

                except Exception as backup_err:
                    await safe_send_message(
                        context,
                        chat_id,
                        f"❌ خطای بکاپ: {str(backup_err)}",
                    )
                    decrement_yt_downloads(chat_id)

            finally:
                for file_path in downloaded_files:
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass

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
                    if destination == "server":
                        if upload_to_s3 is None:
                            await safe_send_message(
                                context,
                                chat_id,
                                "❌ سرویس آپلود ابری در دسترس نیست.",
                            )
                            decrement_yt_downloads(chat_id)
                            return

                        await safe_send_message(
                            context,
                            chat_id,
                            "☁️ آپلود در سرور ابری...",
                        )

                        s3_url = await asyncio.to_thread(upload_to_s3, file_path)

                        if s3_url:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"✅ ذخیره شد:\n\n🔗 [لینک]({s3_url})",
                                parse_mode="Markdown",
                            )
                        else:
                            await safe_send_message(
                                context,
                                chat_id,
                                "❌ خطا در آپلود ابری.",
                            )
                            decrement_yt_downloads(chat_id)

                    else:
                        await safe_send_message(
                            context,
                            chat_id,
                            "📤 آپلود فایل صوتی...",
                        )

                        try:
                            file_id = await upload_audio_to_storage_once(
                                context,
                                file_path,
                                f"Audio ID: {video_id}",
                            )

                            send_status = await send_audio_once(
                                context, chat_id, file_id
                            )

                            if send_status == "success":
                                save_cached_video(cache_key, [file_id])
                                await safe_send_message(
                                    context,
                                    chat_id,
                                    "✅ ارسال با موفقیت انجام شد!",
                                )

                            elif send_status == "timeout":
                                await safe_send_message(
                                    context,
                                    chat_id,
                                    "⚠️ فایل صوتی احتمالاً ارسال شده، اما چون تایم‌اوت رخ داد در دیتابیس ذخیره نشد.",
                                )

                            else:
                                await safe_send_message(
                                    context,
                                    chat_id,
                                    "❌ خطا در ارسال صوت.",
                                )

                        except TimedOut:
                            await safe_send_message(
                                context,
                                chat_id,
                                "⚠️ فایل صوتی هنگام آپلود دچار تایم‌اوت شد. ممکن است ارسال شده باشد، اما در دیتابیس ذخیره نشد.",
                            )

                        except Exception as aud_err:
                            print(f"❌ Audio send/upload error: {aud_err}")
                            await safe_send_message(
                                context,
                                chat_id,
                                "❌ خطا در ارسال صوت.",
                            )

                else:
                    await safe_send_message(
                        context,
                        chat_id,
                        "❌ دانلود شکست خورد.",
                    )
                    decrement_yt_downloads(chat_id)

            except Exception as send_err:
                await safe_send_message(
                    context,
                    chat_id,
                    f"❌ خطا: {str(send_err)}",
                )
                decrement_yt_downloads(chat_id)

            finally:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass

    except Exception as e:
        progress_dict["is_finished"] = True
        await safe_send_message(context, chat_id, f"❌ خطا: {str(e)}")
        decrement_yt_downloads(chat_id)

    finally:
        progress_dict["is_finished"] = True
        updater_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await updater_task


async def yt_worker(queue: asyncio.Queue):
    while True:
        task = await queue.get()

        try:
            await execute_yt_download(
                context=task["context"],
                url=task["url"],
                chat_id=task["chat_id"],
                format_type=task["format_type"],
                destination=task["destination"],
                status_msg=task["status_msg"],
            )
        except Exception as e:
            print(f"Worker Exception: {e}")
        finally:
            queue.task_done()


def ensure_workers_started():
    global _workers_started

    if not _workers_started:
        for _ in range(MAX_NORMAL_DOWNLOADS):
            asyncio.create_task(yt_worker(yt_normal_queue))

        for _ in range(MAX_VIP_DOWNLOADS):
            asyncio.create_task(yt_worker(yt_vip_queue))

        _workers_started = True


# -------------------- Queue Entry Point -------------------- #


async def background_yt_download(
    context,
    url: str,
    chat_id: str,
    format_type: str,
    destination: str = "telegram",
):
    video_id = extract_yt_id(url)
    cache_key = f"{video_id}_{format_type}_{destination}"

    if destination == "telegram":
        cached_files = get_cached_video(cache_key)

        if cached_files:
            await send_cached_files(context, chat_id, cached_files, format_type)
            increment_yt_video_view(cache_key)
            return

    user_is_vip = is_vip(chat_id)
    active_queue = yt_vip_queue if user_is_vip else yt_normal_queue
    queue_position = active_queue.qsize()

    if queue_position > 0:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ درخواست شما ثبت شد.\nسرور شلوغ است. شما در موقعیت {queue_position + 1} از صف قرار گرفتید...",
        )
    else:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ درخواست شما ثبت شد و پردازش به زودی آغاز می‌گردد...",
        )

    ensure_workers_started()

    await active_queue.put(
        {
            "context": context,
            "url": url,
            "chat_id": chat_id,
            "format_type": format_type,
            "destination": destination,
            "status_msg": status_msg,
        }
    )


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

        set_state(chat_id, "waiting_yt_selection", videos=results)

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

        set_state(chat_id, "waiting_yt_selection", videos=results)

        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
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

        res_text = "🔎 نتایج جستجو:\n\n"
        keyboard = []

        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])

        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_yt_selection", videos=results)

        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    elif step == "waiting_yt_selection":
        if text.startswith("📥 دانلود ویدیو "):
            if not check_user_limit(chat_id):
                await update.message.reply_text(
                    "❌ محدودیت دانلود روزانه شما به پایان رسیده است."
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

                set_state(chat_id, "waiting_yt_format", yt_url=selected_video["url"])

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
            set_state(chat_id, "waiting_yt_format", yt_url=text)

            await update.message.reply_text(
                "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        if not check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما به پایان رسیده است."
            )
            return

        set_state(chat_id, "waiting_yt_destination", yt_url=text, format=dl_format)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 آپلود مستقیم بله",
                        callback_data="ytdest_telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "☁️ آپلود در سرور ابری ویژه Pro ⭐️",
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

        if not check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما به پایان رسیده است."
            )
            return

        format_type = "video" if text == BTN_YT_VIDEO else "audio"

        set_state(chat_id, "waiting_yt_destination", yt_url=url, format=format_type)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 آپلود مستقیم بله",
                        callback_data="ytdest_telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "☁️ آپلود در سرور ابری ویژه Pro ⭐️",
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
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = str(query.message.chat_id)

    if data not in ["ytdest_telegram", "ytdest_server"]:
        return

    user_state = get_state(chat_id)

    if not user_state or user_state.get("step") != "waiting_yt_destination":
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    url = user_state.get("yt_url")
    format_type = user_state.get("format")

    if data == "ytdest_server":
        if not is_vip(chat_id):
            await query.edit_message_text(
                "❌ این قابلیت فقط مخصوص کاربران ویژه Pro ⭐️ می‌باشد."
            )
            return

        destination = "server"
    else:
        destination = "telegram"

    await query.edit_message_text("✅ درخواست ثبت شد. در حال انتقال به صف دانلود...")

    clear_state(chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔙 بازگشت به منوی اصلی",
        reply_markup=get_main_menu_keyboard(),
    )

    increment_yt_downloads(chat_id)

    asyncio.create_task(
        background_yt_download(
            context,
            url,
            chat_id,
            format_type,
            destination,
        )
    )
