import asyncio
import re
import os
from core.database import is_vip, get_yt_downloads, save_cached_video
from .config import STORAGE_CHANNEL_ID
from core.limits import get_limit
from services.zip_utils import format_merge_instructions, part_display_filename


async def check_user_limit(chat_id: str) -> bool:
    vip_status = await is_vip(chat_id)
    limit = get_limit("youtube_download", vip_status)
    usage = await get_yt_downloads(chat_id)
    return usage < limit


def extract_yt_id(url: str):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else url


def parse_format_from_cache_key(cache_key: str) -> str:
    if "_audio_" in cache_key or cache_key.endswith("_audio"):
        return "audio_zip"
    if "_video_zip" in cache_key or "_zip" in cache_key:
        return "video_zip"
    if "_video_" in cache_key:
        return "video"
    return "video_zip"


def parse_quality_from_cache_key(cache_key: str) -> str:
    parts = cache_key.split("_")
    for p in reversed(parts):
        if p.isdigit() and len(p) <= 4:
            return p
    return "480"


async def save_to_global_cache(
    cache_key: str,
    video_id: str,
    file_ids: list,
    title: str | None = None,
    channel_name: str | None = None,
):
    await save_cached_video(
        cache_key,
        file_ids,
        title=title or f"ویدیو {video_id}",
        channel_name=channel_name or "ناشناس",
        yt_video_id=video_id,
        format_type=parse_format_from_cache_key(cache_key),
        quality=parse_quality_from_cache_key(cache_key),
    )


def format_duration(seconds: float) -> str:
    try:
        total_seconds = int(seconds)
    except Exception:
        return "نامشخص"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ساعت")
    if minutes:
        parts.append(f"{minutes} دقیقه")
    if secs or not parts:
        parts.append(f"{secs} ثانیه")
    return " ".join(parts)


def format_size(bytes_size: int) -> str:
    try:
        mb = bytes_size / (1024 * 1024)
        if mb >= 1024:
            gb = mb / 1024
            return f"{gb:.2f} گیگابایت"
        return f"{mb:.1f} مگابایت"
    except Exception:
        return "نامشخص"


def get_waiting_count(semaphore: asyncio.Semaphore, max_concurrent: int) -> int:
    try:
        waiters = len(semaphore._waiters) if semaphore._waiters else 0
        running = max_concurrent - semaphore._value
        return max(0, running + waiters)
    except Exception:
        return 0


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


async def send_document_once(context, chat_id: str, file_id: str):
    try:
        await context.bot.send_document(chat_id=chat_id, document=file_id)
        return True
    except Exception as e:
        print(f"⚠️ Error sending document file_id to user {chat_id}: {e}")
        return False


async def upload_document_to_storage_once(
    context, file_path: str, caption: str, filename: str | None = None
):
    with open(file_path, "rb") as doc:
        channel_msg = await context.bot.send_document(
            chat_id=STORAGE_CHANNEL_ID,
            document=doc,
            filename=filename,
            caption=caption,
            read_timeout=120,
            write_timeout=120,
            connect_timeout=30,
            pool_timeout=30,
        )
    return channel_msg.document.file_id


async def process_and_send_document_parts(
    context,
    chat_id: str,
    result_files: list,
    label: str,
    cache_key: str,
    archive_basename: str = "archive",
    split_method: str = "single",
    video_id: str | None = None,
    title: str | None = None,
    channel_name: str | None = None,
):
    uploaded_file_ids = []
    total_parts = len(result_files)
    part_msg = f" (شامل {total_parts} پارت)" if total_parts > 1 else ""
    await context.bot.send_message(
        chat_id=chat_id, text=f"📤 در حال آپلود فایل ZIP{part_msg}..."
    )

    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id, text=f"📤 آپلود پارت {idx} از {total_parts}..."
            )

        display_name = part_display_filename(
            file_path, archive_basename, idx, total_parts, split_method
        )
        caption = f"{label} | {display_name}"
        try:
            current_file_id = await upload_document_to_storage_once(
                context=context,
                file_path=file_path,
                caption=caption,
                filename=display_name,
            )
            send_success = await send_document_once(context, chat_id, current_file_id)
            if not send_success:
                raise Exception("خطا در فوروارد/ارسال به کاربر")
            uploaded_file_ids.append(current_file_id)
        except Exception as e:
            print(f"❌ Error uploading/sending zip part {idx}: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ متاسفانه در آپلود یا ارسال پارت ZIP {idx} مشکلی پیش آمد. عملیات لغو شد.",
            )
            raise e
        await asyncio.sleep(1)

    if len(uploaded_file_ids) == total_parts:
        await save_cached_video(
            cache_key,
            uploaded_file_ids,
            title=title,
            channel_name=channel_name,
            yt_video_id=video_id,
            format_type=parse_format_from_cache_key(cache_key),
            quality=parse_quality_from_cache_key(cache_key),
        )
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=format_merge_instructions(
                    archive_basename, total_parts, split_method
                ),
            )
        await context.bot.send_message(chat_id=chat_id, text="✅ پایان عملیات ارسال ZIP.")


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
    title: str | None = None,
    channel_name: str | None = None,
):
    uploaded_file_ids = []
    total_parts = len(result_files)
    part_msg = f" (شامل {total_parts} پارت)" if total_parts > 1 else ""
    await context.bot.send_message(
        chat_id=chat_id, text=f"📤 در حال آپلود ویدیو{part_msg}..."
    )

    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id, text=f"📤 آپلود پارت {idx} از {total_parts}..."
            )
        caption = f"Video ID: {video_id} | Part {idx}/{total_parts}"
        try:
            current_file_id = await upload_video_to_storage_once(
                context=context, file_path=file_path, caption=caption
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
        await save_cached_video(
            cache_key,
            uploaded_file_ids,
            title=title,
            channel_name=channel_name,
            yt_video_id=video_id,
            format_type=parse_format_from_cache_key(cache_key),
            quality=parse_quality_from_cache_key(cache_key),
        )
        await context.bot.send_message(chat_id=chat_id, text="✅ پایان عملیات ارسال.")


async def process_and_send_backup_video_parts(
    context,
    chat_id: str,
    result_files: list,
    video_id: str,
    cache_key: str,
    title: str | None = None,
    channel_name: str | None = None,
):
    uploaded_file_ids = []
    total_parts = len(result_files)
    for idx, file_path in enumerate(result_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id, text=f"📤 ارسال پارت بکاپ {idx} از {total_parts}..."
            )
        caption = f"Video ID: {video_id} (Backup) | Part {idx}/{total_parts}"
        try:
            current_file_id = await upload_video_to_storage_once(
                context=context, file_path=file_path, caption=caption
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
        await save_cached_video(
            cache_key,
            uploaded_file_ids,
            title=title,
            channel_name=channel_name,
            yt_video_id=video_id,
            format_type=parse_format_from_cache_key(cache_key),
            quality=parse_quality_from_cache_key(cache_key),
        )
        await context.bot.send_message(
            chat_id=chat_id, text="✅ پایان عملیات ارسال بکاپ."
        )


async def send_cached_files(
    context, chat_id: str, cached_files: list, format_type: str
):
    await context.bot.send_message(
        chat_id=chat_id, text="✅ این فایل در سرور موجود است. در حال ارسال فوری..."
    )
    total_parts = len(cached_files)
    for idx, file_id in enumerate(cached_files, 1):
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id, text=f"📤 ارسال پارت {idx} از {total_parts}..."
            )
        if format_type.endswith("_zip"):
            await send_document_once(context, chat_id, file_id)
        elif format_type == "video":
            await send_video_once(context, chat_id, file_id)
        else:
            await send_audio_once(context, chat_id, file_id)
        await asyncio.sleep(1)
