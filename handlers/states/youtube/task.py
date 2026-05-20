# handlers/states/youtube/task.py

import os
import asyncio
from core.database import (
    is_vip,
    decrement_yt_downloads,
    get_cached_video,
    save_cached_video,
    increment_yt_video_view,
    reduce_cloud_storage,
    add_cloud_file,
    get_available_cloud_mb,  # تغییر نام به تابع صحیح
)
from services.youtube import (
    download_youtube_video,
    download_youtube_audio,
    split_video_if_needed,
    get_video_info,
    get_video_filesize,
)
from services.telegram_backup import download_from_telegram_bot
from services.zip_utils import build_zip_and_split

try:
    from services.parspack_s3 import upload_to_s3
except ImportError:
    upload_to_s3 = None

from .config import (
    telegram_normal_semaphore,
    telegram_vip_semaphore,
    server_normal_semaphore,
    server_vip_semaphore,
    MAX_NORMAL_DOWNLOADS,
    MAX_VIP_DOWNLOADS,
)
from .helpers import (
    extract_yt_id,
    send_cached_files,
    format_duration,
    format_size,
    get_waiting_count,
    process_and_send_video_parts,
    process_and_send_backup_video_parts,
    process_and_send_document_parts,
    upload_audio_to_storage_once,
    send_audio_once,
)


async def background_yt_download(
    context,
    url: str,
    chat_id: str,
    format_type: str,
    destination: str = "telegram",
    quality: str = "480",
):
    video_id = extract_yt_id(url)
    effective_format = (
        f"{format_type}_zip" if destination == "telegram" else format_type
    )
    cache_key = f"{video_id}_{effective_format}_{destination}_{quality}"

    # =========================================
    # کش
    # =========================================

    if destination == "telegram":
        cached_files = await get_cached_video(cache_key)

        if cached_files:
            await send_cached_files(
                context,
                chat_id,
                cached_files,
                effective_format,
            )

            await increment_yt_video_view(cache_key)

            return

    # =========================================
    # اطلاعات ویدیو
    # =========================================

    info = await asyncio.to_thread(get_video_info, url)

    # =========================================
    # چک سایز قبل دانلود
    # =========================================

    try:
        if format_type == "video":
            format_selector = (
                f"best[height<={quality}][ext=mp4]/best[height<={quality}]/best"
            )
            estimated_size = await asyncio.to_thread(
                get_video_filesize, url, format_selector
            )
        else:
            estimated_size = await asyncio.to_thread(
                get_video_filesize, url, "bestaudio/best"
            )

        limit = (
            1 * 1024 * 1024 * 1024
            if destination == "telegram"
            else 1 * 1024 * 1024 * 1024
        )

        if estimated_size:
            # 1. چک کردن محدودیت کلی سرور/تلگرام
            if estimated_size > limit:
                size_mb = round(estimated_size / (1024 * 1024), 1)
                limit_mb = round(limit / (1024 * 1024), 1)

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"❌ حجم فایل حدود {size_mb} مگابایت است.\n\n"
                        f"حداکثر حجم مجاز {limit_mb} مگابایت است."
                    ),
                )

                await decrement_yt_downloads(chat_id)

                return

            # 2. چک کردن موجودی فضای ابری کاربر
            if destination == "server":
                user_storage_mb = await get_available_cloud_mb(chat_id)
                if user_storage_mb is None or user_storage_mb <= 0:
                    user_storage_mb = 0

                estimated_size_mb = round(estimated_size / (1024 * 1024), 2)

                if user_storage_mb <= 0 or estimated_size_mb > user_storage_mb:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"❌ فضای ابری شما کافی نیست!\n\n"
                            f"حجم تخمینی فایل: {estimated_size_mb} مگابایت\n"
                            f"فضای باقیمانده شما: {round(user_storage_mb, 2)} مگابایت\n\n"
                            f"لطفاً برای ارتقای حجم ابری خود از طریق منوی فروشگاه اقدام کنید."
                        ),
                    )
                    await decrement_yt_downloads(chat_id)
                    return

    except Exception as e:
        print(f"⚠️ Error checking filesize: {e}")

    # =========================================
    # thumbnail
    # =========================================

    if info and info.get("thumbnail"):
        duration_text = format_duration(info.get("duration", 0))
        size_text = format_size(estimated_size) if estimated_size else None

        caption = (
            f"🎥 **{info['title']}**\n"
            f"👤 کانال: {info['uploader']}\n"
            f"⏱ زمان: {duration_text}\n"
            + (f"💾 حجم فایل: {size_text}\n" if size_text else "")
            + "\n"
            f"⏳ در حال آماده‌سازی برای دانلود..."
        )

        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=info["thumbnail"],
                caption=caption,
                parse_mode="Markdown",
            )
        except Exception:
            pass

    # =========================================
    # semaphore
    # =========================================

    user_is_vip = await is_vip(chat_id)

    if destination == "telegram":
        active_semaphore = (
            telegram_vip_semaphore if user_is_vip else telegram_normal_semaphore
        )
    else:
        active_semaphore = (
            server_vip_semaphore if user_is_vip else server_normal_semaphore
        )

    max_concurrent = MAX_VIP_DOWNLOADS if user_is_vip else MAX_NORMAL_DOWNLOADS

    waiting_count = get_waiting_count(
        active_semaphore,
        max_concurrent,
    )

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
            progress_dict = {
                "text": "شروع پردازش...",
                "is_finished": False,
            }

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
                # =========================================
                # VIDEO
                # =========================================

                if format_type == "video":
                    downloaded_files = []
                    zip_artifacts = []

                    try:
                        max_size = (
                            1 * 1024 * 1024 * 1024
                            if destination == "telegram"
                            else 1 * 1024 * 1024 * 1024
                        )
                        raw_file = await asyncio.to_thread(
                            download_youtube_video,
                            url,
                            quality,
                            progress_dict,
                            max_size,
                        )

                        progress_dict["is_finished"] = True

                        # =========================
                        # فایل بزرگ
                        # =========================

                        if raw_file == "TOO_LARGE":
                            if destination == "telegram":
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ حجم فایل بیش از 1 گیگابایت است.",
                                )
                            else:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ حجم فایل بیش از 1 گیگابایت است.",
                                )

                            await decrement_yt_downloads(chat_id)

                            return

                        # =========================

                        elif raw_file and isinstance(raw_file, str):
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg.message_id,
                                text="⏳ در حال آماده‌سازی ویدیو...",
                            )

                            if destination == "telegram":
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="📦 در حال ساخت ZIP و تقسیم به پارت‌های 20MB...",
                                )
                                zip_basename = f"youtube_{video_id}_{quality}p"
                                zip_parts, archive_basename, split_method = (
                                    await asyncio.to_thread(
                                        build_zip_and_split,
                                        raw_file,
                                        os.path.dirname(raw_file) or ".",
                                        zip_basename,
                                        20 * 1024 * 1024,
                                    )
                                )
                                zip_artifacts.extend(zip_parts)
                                if split_method == "concat":
                                    full_zip = os.path.join(
                                        os.path.dirname(raw_file) or ".",
                                        f"{archive_basename}.zip",
                                    )
                                    if os.path.isfile(full_zip):
                                        zip_artifacts.append(full_zip)
                                result = zip_parts
                            else:
                                result = [raw_file]

                            downloaded_files.extend(result)

                            # =========================
                            # upload to cloud
                            # =========================

                            if destination == "server":
                                # =================================
                                # چک فضای ابری قبل از آپلود ویدیو
                                # =================================
                                user_storage_mb = await get_available_cloud_mb(chat_id)
                                if user_storage_mb is None or user_storage_mb <= 0:
                                    user_storage_mb = 0

                                # محاسبه کل حجم فایل‌های تقسیم‌شده
                                total_video_size_mb = 0
                                for file_path in result:
                                    total_video_size_mb += round(
                                        os.path.getsize(file_path) / (1024 * 1024), 2
                                    )

                                if (
                                    user_storage_mb <= 0
                                    or total_video_size_mb > user_storage_mb
                                ):
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=(
                                            f"❌ فضای ابری شما کافی نیست!\n\n"
                                            f"حجم کل ویدیو: {total_video_size_mb} مگابایت\n"
                                            f"فضای باقیمانده شما: {round(user_storage_mb, 2)} مگابایت\n\n"
                                            f"لطفاً برای ارتقای حجم ابری خود از طریق منوی فروشگاه اقدام کنید."
                                        ),
                                    )
                                    await decrement_yt_downloads(chat_id)
                                    return

                                # =================================

                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="☁️ آپلود در فضای ابری ...",
                                )

                                progress_dict["is_finished"] = False
                                progress_dict["text"] = "☁️ شروع آپلود ابری..."

                                updater_task = asyncio.create_task(
                                    update_progress_message()
                                )

                                s3_links = []
                                total_size_mb = 0

                                for file_path in result:
                                    s3_url = await asyncio.to_thread(
                                        upload_to_s3,
                                        file_path,
                                        None,
                                        progress_dict,
                                    )

                                    if s3_url:
                                        file_size_mb = round(
                                            os.path.getsize(file_path) / (1024 * 1024),
                                            2,
                                        )
                                        file_name = os.path.basename(file_path)
                                        total_size_mb += file_size_mb

                                        await add_cloud_file(
                                            chat_id, file_name, file_size_mb, s3_url
                                        )
                                        s3_links.append(s3_url)

                                progress_dict["is_finished"] = True

                                if s3_links:
                                    await reduce_cloud_storage(chat_id, total_size_mb)

                                    links_text = "\n\n".join(
                                        [
                                            f"🔗 [لینک دانلود فایل]({link})"
                                            for link in s3_links
                                        ]
                                    )

                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"✅ فایل با موفقیت در فضای ابری ذخیره شد.\n\n📉 حجم کسر شده: {total_size_mb} مگابایت\n⏳ تاریخ انقضای لینک‌ها: 3 ساعت\n\n{links_text}",
                                        parse_mode="Markdown",
                                    )

                                else:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ خطا در آپلود ابری.",
                                    )

                                    await decrement_yt_downloads(chat_id)

                            # =========================
                            # telegram upload
                            # =========================

                            else:
                                # Telegram destination always sends ZIP as documents
                                await process_and_send_document_parts(
                                    context,
                                    chat_id,
                                    result,
                                    label=f"Video ID: {video_id}",
                                    cache_key=cache_key,
                                    archive_basename=archive_basename,
                                    split_method=split_method,
                                )

                        else:
                            raise Exception("Download failed")

                    except Exception as send_err:
                        print(f"❌ Video error: {send_err}")

                        error_text = str(send_err).lower()

                        # =========================================
                        # جلوگیری از backup برای فایل بزرگ
                        # =========================================

                        if raw_file == "TOO_LARGE" or any(
                            keyword in error_text
                            for keyword in [
                                "too large",
                                "max-filesize",
                                "1000",
                                "size",
                                "exceed",
                                "limit",
                            ]
                        ):
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ حجم فایل بیشتر از 1 گیگابایت است.",
                            )

                            await decrement_yt_downloads(chat_id)

                            return

                        # =========================================

                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="⚠️ تلاش از طریق سرور بکاپ ... ⏳",
                        )

                        try:
                            backup_file = await download_from_telegram_bot(url)

                            if backup_file and os.path.exists(backup_file):
                                # =====================================
                                # چک سایز بکاپ
                                # =====================================

                                backup_size = os.path.getsize(backup_file)

                                if backup_size > 1 * 1024 * 1024 * 1024:
                                    try:
                                        os.remove(backup_file)
                                    except:
                                        pass

                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ فایل بکاپ بزرگ‌تر از 1 گیگابایت است.",
                                    )

                                    await decrement_yt_downloads(chat_id)

                                    return

                                # =====================================

                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="⏳ در حال آماده‌سازی فایل بکاپ...",
                                )

                                if destination == "server":
                                    # =====================================
                                    # چک فضای ابری قبل از آپلود بکاپ
                                    # =====================================
                                    user_storage_mb = await get_available_cloud_mb(
                                        chat_id
                                    )
                                    if user_storage_mb is None or user_storage_mb <= 0:
                                        user_storage_mb = 0

                                    backup_size_mb = round(
                                        backup_size / (1024 * 1024), 2
                                    )

                                    if (
                                        user_storage_mb <= 0
                                        or backup_size_mb > user_storage_mb
                                    ):
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text=(
                                                f"❌ فضای ابری شما کافی نیست!\n\n"
                                                f"حجم فایل بکاپ: {backup_size_mb} مگابایت\n"
                                                f"فضای باقیمانده شما: {round(user_storage_mb, 2)} مگابایت\n\n"
                                                f"لطفاً برای ارتقای حجم ابری خود از طریق منوی فروشگاه اقدام کنید."
                                            ),
                                        )
                                        await decrement_yt_downloads(chat_id)
                                        return

                                    # =====================================

                                    progress_dict["is_finished"] = False

                                    updater_task = asyncio.create_task(
                                        update_progress_message()
                                    )

                                    s3_url = await asyncio.to_thread(
                                        upload_to_s3,
                                        backup_file,
                                        None,
                                        progress_dict,
                                    )

                                    progress_dict["is_finished"] = True

                                    if s3_url:
                                        backup_size_mb = round(
                                            backup_size / (1024 * 1024), 2
                                        )
                                        file_name = os.path.basename(backup_file)

                                        await add_cloud_file(
                                            chat_id, file_name, backup_size_mb, s3_url
                                        )
                                        await reduce_cloud_storage(
                                            chat_id, backup_size_mb
                                        )

                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text=f"✅ ذخیره موفق در فضای ابری (بکاپ):\n\n📉 حجم کسر شده: {backup_size_mb} مگابایت\n\n🔗 [لینک دانلود]({s3_url})",
                                            parse_mode="Markdown",
                                        )

                                    else:
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text="❌ خطا در آپلود ابری.",
                                        )

                                        await decrement_yt_downloads(chat_id)

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
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ سرور بکاپ ناموفق بود.",
                                )

                                await decrement_yt_downloads(chat_id)

                        except Exception as backup_err:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"❌ خطای بکاپ: {str(backup_err)}",
                            )

                            await decrement_yt_downloads(chat_id)

                    finally:
                        for file_path in downloaded_files:
                            if os.path.exists(file_path):
                                try:
                                    await asyncio.to_thread(os.remove, file_path)
                                except Exception:
                                    pass
                        for z in zip_artifacts:
                            if z and isinstance(z, str) and os.path.exists(z):
                                try:
                                    await asyncio.to_thread(os.remove, z)
                                except Exception:
                                    pass

                # =========================================
                # AUDIO
                # =========================================

                elif format_type == "audio":
                    file_path = None
                    zip_artifacts = []

                    try:
                        max_size = (
                            1 * 1024 * 1024 * 1024
                            if destination == "telegram"
                            else 1 * 1024 * 1024 * 1024
                        )
                        file_path = await asyncio.to_thread(
                            download_youtube_audio,
                            url,
                            max_size,
                        )

                        progress_dict["is_finished"] = True

                        # =========================
                        # فایل بزرگ
                        # =========================

                        if file_path == "TOO_LARGE":
                            if destination == "telegram":
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ حجم فایل صوتی بیش از 1 گیگابایت است.",
                                )
                            else:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="❌ حجم فایل صوتی بیشتر از 1 گیگابایت است.",
                                )

                            await decrement_yt_downloads(chat_id)

                            return

                        # =========================

                        if (
                            file_path
                            and isinstance(file_path, str)
                            and os.path.exists(file_path)
                        ):
                            # =====================
                            # cloud
                            # =====================

                            if destination == "server":
                                # =================================
                                # چک فضای ابری قبل از آپلود صوت
                                # =================================
                                user_storage_mb = await get_available_cloud_mb(chat_id)
                                if user_storage_mb is None or user_storage_mb <= 0:
                                    user_storage_mb = 0

                                audio_size_mb = round(
                                    os.path.getsize(file_path) / (1024 * 1024), 2
                                )

                                if (
                                    user_storage_mb <= 0
                                    or audio_size_mb > user_storage_mb
                                ):
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=(
                                            f"❌ فضای ابری شما کافی نیست!\n\n"
                                            f"حجم فایل صوتی: {audio_size_mb} مگابایت\n"
                                            f"فضای باقیمانده شما: {round(user_storage_mb, 2)} مگابایت\n\n"
                                            f"لطفاً برای ارتقای حجم ابری خود از طریق منوی فروشگاه اقدام کنید."
                                        ),
                                    )
                                    await decrement_yt_downloads(chat_id)
                                    return

                                # =================================

                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="☁️ آپلود در سرور ابری...",
                                )

                                progress_dict["is_finished"] = False

                                updater_task = asyncio.create_task(
                                    update_progress_message()
                                )

                                s3_url = await asyncio.to_thread(
                                    upload_to_s3,
                                    file_path,
                                    None,
                                    progress_dict,
                                )

                                progress_dict["is_finished"] = True

                                if s3_url:
                                    audio_size_mb = round(
                                        os.path.getsize(file_path) / (1024 * 1024), 2
                                    )
                                    file_name = os.path.basename(file_path)

                                    await add_cloud_file(
                                        chat_id, file_name, audio_size_mb, s3_url
                                    )
                                    await reduce_cloud_storage(chat_id, audio_size_mb)

                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"✅ فایل صوتی با موفقیت ذخیره شد:\n\n📉 حجم کسر شده: {audio_size_mb} مگابایت\n\n🔗 [لینک دانلود]({s3_url})",
                                        parse_mode="Markdown",
                                    )

                                else:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ خطا در آپلود ابری.",
                                    )

                                    await decrement_yt_downloads(chat_id)

                            # =====================
                            # telegram
                            # =====================

                            else:
                                # Telegram destination: ZIP audio + split to 20MB documents
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text="📦 در حال ساخت ZIP و تقسیم به پارت‌های 20MB...",
                                )
                                zip_basename = f"youtube_audio_{video_id}"
                                zip_parts, archive_basename, split_method = (
                                    await asyncio.to_thread(
                                        build_zip_and_split,
                                        file_path,
                                        os.path.dirname(file_path) or ".",
                                        zip_basename,
                                        20 * 1024 * 1024,
                                    )
                                )
                                zip_artifacts.extend(zip_parts)
                                if split_method == "concat":
                                    full_zip = os.path.join(
                                        os.path.dirname(file_path) or ".",
                                        f"{archive_basename}.zip",
                                    )
                                    if os.path.isfile(full_zip):
                                        zip_artifacts.append(full_zip)

                                await process_and_send_document_parts(
                                    context,
                                    chat_id,
                                    zip_parts,
                                    label=f"Audio ID: {video_id}",
                                    cache_key=cache_key,
                                    archive_basename=archive_basename,
                                    split_method=split_method,
                                )

                        else:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ دانلود شکست خورد.",
                            )

                            await decrement_yt_downloads(chat_id)

                    except Exception as send_err:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"❌ خطا: {str(send_err)}",
                        )

                        await decrement_yt_downloads(chat_id)

                    finally:
                        if file_path and os.path.exists(file_path):
                            try:
                                await asyncio.to_thread(
                                    os.remove,
                                    file_path,
                                )
                            except:
                                pass
                        for z in zip_artifacts:
                            if z and isinstance(z, str) and os.path.exists(z):
                                try:
                                    await asyncio.to_thread(os.remove, z)
                                except Exception:
                                    pass

            except Exception as e:
                progress_dict["is_finished"] = True

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ خطا: {str(e)}",
                )

                await decrement_yt_downloads(chat_id)

            finally:
                progress_dict["is_finished"] = True

                updater_task.cancel()

    except Exception as e:
        print(f"Semaphore Error: {e}")

        await decrement_yt_downloads(chat_id)
