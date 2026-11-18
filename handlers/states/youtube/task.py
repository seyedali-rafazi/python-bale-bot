# handlers/states/youtube/task.py

import os
import asyncio
import logging
from core.task_utils import get_file_size_async, remove_files_async
from core.database import (
    is_vip,
    decrement_yt_downloads,
    get_cached_video,
    get_cache_row_metadata,
    get_cached_video_with_meta,
    save_cached_video,
    increment_yt_video_view,
    record_cloud_upload,
    record_cloud_uploads,
    get_available_cloud_mb,
    reserve_cloud_quota,
    release_cloud_quota,
    log_upload_failed,
)

logger = logging.getLogger(__name__)
from services.youtube import (
    async_download_youtube_video,
    async_download_youtube_audio,
    split_video_if_needed,
    get_video_info_cached,
    uploaded_at_from_video_info,
    get_video_filesize_cached,
)
from services.zip_utils import build_zip_and_split

try:
    from services.parspack_s3 import async_upload_to_s3_with_key, upload_to_s3, upload_to_s3_with_key
except ImportError:
    async_upload_to_s3_with_key = None
    upload_to_s3 = None
    upload_to_s3_with_key = None

from .config import (
    telegram_normal_semaphore,
    telegram_vip_semaphore,
    server_normal_semaphore,
    server_vip_semaphore,
    MAX_NORMAL_DOWNLOADS,
    MAX_VIP_DOWNLOADS,
)
from core.yt_moderation import (
    MSG_BLOCKED_CHANNEL,
    check_video_info_allowed,
)
from .helpers import (
    ForwardStatus,
    extract_yt_id,
    forward_file_id_to_user,
    send_cached_files,
    format_duration,
    format_size,
    get_waiting_count,
    process_and_send_document_parts,
    process_and_send_mp4_videos_no_cache,
    upload_audio_to_storage_once,
    send_audio_once,
    save_to_global_cache,
)


def _effective_format(format_type: str, destination: str, delivery_mode: str) -> str:
    if destination != "telegram":
        return format_type
    if format_type == "audio":
        return "audio_zip"
    if format_type == "video" and delivery_mode == "zip":
        return "video_zip"
    return format_type


def _use_youtube_cache(destination: str, format_type: str, delivery_mode: str) -> bool:
    if destination != "telegram":
        return False
    if format_type == "video" and delivery_mode == "video":
        return False
    return True


async def background_yt_download(
    context,
    url: str,
    chat_id: str,
    format_type: str,
    destination: str = "telegram",
    quality: str = "480",
    delivery_mode: str = "zip",
    *,
    estimated_size: int | None = None,
):
    video_id = extract_yt_id(url)
    effective_format = _effective_format(format_type, destination, delivery_mode)
    cache_key = f"{video_id}_{effective_format}_{destination}_{quality}"

    # =========================================
    # کش
    # =========================================

    if _use_youtube_cache(destination, format_type, delivery_mode):
        cached_files, meta = await get_cached_video_with_meta(cache_key)

        if cached_files:
            has_meta = bool(
                meta
                and meta.get("title")
                and meta.get("uploader")
                and meta.get("uploaded_at")
            )
            info_cached = meta if has_meta else await get_video_info_cached(url)

            if not await check_video_info_allowed(info_cached):
                await context.bot.send_message(
                    chat_id=chat_id, text=MSG_BLOCKED_CHANNEL
                )
                await decrement_yt_downloads(chat_id)
                return

            await send_cached_files(
                context,
                chat_id,
                cached_files,
                (meta.get("format_type") if meta else None) or effective_format,
            )
            await increment_yt_video_view(cache_key)

            if not has_meta and info_cached:
                await save_to_global_cache(
                    cache_key,
                    video_id,
                    cached_files,
                    title=info_cached.get("title"),
                    channel_name=info_cached.get("uploader"),
                    uploaded_at=uploaded_at_from_video_info(info_cached),
                    resolve_missing_meta=False,
                )

            return

    # =========================================
    # اطلاعات ویدیو + VIP + حجم ابری (هم‌زمان)
    # =========================================

    if destination == "server":
        info, user_is_vip, user_storage_mb_prefetched = await asyncio.gather(
            get_video_info_cached(url),
            is_vip(chat_id),
            get_available_cloud_mb(chat_id),
        )
    else:
        info, user_is_vip = await asyncio.gather(
            get_video_info_cached(url),
            is_vip(chat_id),
        )
        user_storage_mb_prefetched = None

    if not await check_video_info_allowed(info):
        await context.bot.send_message(chat_id=chat_id, text=MSG_BLOCKED_CHANNEL)
        await decrement_yt_downloads(chat_id)
        return

    # =========================================
    # چک سایز قبل دانلود
    # =========================================

    try:
        if estimated_size is None:
            if format_type == "video":
                estimated_size = await get_video_filesize_cached(url, quality)
            else:
                estimated_size = await get_video_filesize_cached(url, "bestaudio")

        limit = 1 * 1024 * 1024 * 1024

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
                user_storage_mb = user_storage_mb_prefetched
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
        logger.warning("Error checking filesize: %s", e)

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

            async def _stop_updater_task(task: asyncio.Task | None) -> None:
                progress_dict["is_finished"] = True
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass

            updater_task = asyncio.create_task(update_progress_message())

            try:
                # =========================================
                # VIDEO
                # =========================================

                if format_type == "video":
                    downloaded_files = []
                    zip_artifacts = []

                    raw_file = None
                    try:
                        max_size = 1 * 1024 * 1024 * 1024
                        raw_file = await async_download_youtube_video(
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
                                if delivery_mode == "zip":
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="📦 در حال ساخت ZIP و تقسیم به پارت‌های 50MB...",
                                    )
                                    zip_basename = f"youtube_{video_id}_{quality}p"
                                    (
                                        zip_parts,
                                        archive_basename,
                                        split_method,
                                    ) = await asyncio.to_thread(
                                        build_zip_and_split,
                                        raw_file,
                                        os.path.dirname(raw_file) or ".",
                                        zip_basename,
                                        50 * 1024 * 1024,
                                    )
                                    zip_artifacts.extend(zip_parts)
                                    if split_method == "concat":
                                        full_zip = os.path.join(
                                            os.path.dirname(raw_file) or ".",
                                            f"{archive_basename}.zip",
                                        )
                                        if await asyncio.to_thread(os.path.isfile, full_zip):
                                            zip_artifacts.append(full_zip)
                                    result = zip_parts
                                else:
                                    archive_basename = ""
                                    split_method = "single"
                                    result = await split_video_if_needed(raw_file)
                            else:
                                result = [raw_file]

                            downloaded_files.extend(result)

                            # =========================
                            # upload to cloud
                            # =========================

                            if destination == "server":
                                # =================================
                                # چک و رزرو اتمیک فضای ابری قبل از آپلود ویدیو
                                # =================================
                                total_video_size_mb = 0.0
                                for file_path in result:
                                    total_video_size_mb += round(
                                        (await get_file_size_async(file_path)) / (1024 * 1024), 2
                                    )

                                reserved = await reserve_cloud_quota(chat_id, total_video_size_mb)
                                if not reserved:
                                    user_storage_mb = await get_available_cloud_mb(chat_id)
                                    if user_storage_mb is None or user_storage_mb <= 0:
                                        user_storage_mb = 0
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

                                await _stop_updater_task(updater_task)
                                progress_dict["is_finished"] = False
                                progress_dict["text"] = "☁️ شروع آپلود ابری..."

                                updater_task = asyncio.create_task(
                                    update_progress_message()
                                )

                                s3_links = []
                                cloud_records: list[tuple[str, float, str, str | None]] = []
                                total_size_mb = 0.0
                                upload_fn = upload_to_s3_with_key or upload_to_s3

                                try:
                                    for file_path in result:
                                        if upload_to_s3_with_key is not None:
                                            if async_upload_to_s3_with_key is not None:
                                                s3_url, s3_key = await async_upload_to_s3_with_key(
                                                    file_path,
                                                    None,
                                                    progress_dict,
                                                    upload_fn=upload_to_s3_with_key,
                                                )
                                            else:
                                                s3_url, s3_key = await asyncio.to_thread(
                                                    upload_to_s3_with_key,
                                                    file_path,
                                                    None,
                                                    progress_dict,
                                                )
                                        else:
                                            s3_url = await asyncio.to_thread(
                                                upload_fn,
                                                file_path,
                                                None,
                                                progress_dict,
                                            )
                                            s3_key = None

                                        if s3_url:
                                            file_size_mb = round(
                                                (await get_file_size_async(file_path)) / (1024 * 1024),
                                                2,
                                            )
                                            file_name = os.path.basename(file_path)
                                            total_size_mb += file_size_mb
                                            cloud_records.append((file_name, file_size_mb, s3_url, s3_key))
                                            s3_links.append(s3_url)
                                except Exception:
                                    await release_cloud_quota(chat_id, total_video_size_mb)
                                    raise

                                progress_dict["is_finished"] = True

                                if s3_links:
                                    diff = total_video_size_mb - total_size_mb
                                    if diff > 0:
                                        await release_cloud_quota(chat_id, diff)
                                    await record_cloud_uploads(
                                        chat_id, cloud_records, quota_reserved=True
                                    )

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
                                    await release_cloud_quota(chat_id, total_video_size_mb)
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ خطا در آپلود ابری.",
                                    )
                                    await log_upload_failed("youtube", chat_id)
                                    await decrement_yt_downloads(chat_id)

                            # =========================
                            # telegram upload
                            # =========================

                            else:
                                if delivery_mode == "zip":
                                    await process_and_send_document_parts(
                                        context,
                                        chat_id,
                                        result,
                                        label=f"Video ID: {video_id}",
                                        cache_key=cache_key,
                                        archive_basename=archive_basename,
                                        split_method=split_method,
                                        video_id=video_id,
                                        title=info.get("title") if info else None,
                                        channel_name=info.get("uploader")
                                        if info
                                        else None,
                                        uploaded_at=uploaded_at_from_video_info(info),
                                    )
                                else:
                                    await process_and_send_mp4_videos_no_cache(
                                        context,
                                        chat_id,
                                        result,
                                        video_id=video_id,
                                        label=f"Video ID: {video_id}",
                                    )

                        else:
                            raise Exception("Download failed")

                    except Exception as send_err:
                        print(f"❌ Video error: {send_err}")

                        error_text = str(send_err).lower()

                        if raw_file == "TOO_LARGE" or any(
                            keyword in error_text
                            for keyword in (
                                "file is larger than max-filesize",
                                "too large",
                                "max-filesize",
                            )
                        ):
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ حجم فایل بیشتر از 1 گیگابایت است.",
                            )

                            await decrement_yt_downloads(chat_id)

                            return

                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="❌ خطا در دانلود یا ارسال ویدیو. لطفاً بعداً دوباره تلاش کنید.",
                        )
                        await log_upload_failed("youtube", chat_id)
                        await decrement_yt_downloads(chat_id)

                    finally:
                        await remove_files_async(list(dict.fromkeys([*downloaded_files, *zip_artifacts])))

                # =========================================
                # AUDIO
                # =========================================

                elif format_type == "audio":
                    file_path = None
                    zip_artifacts = []

                    try:
                        max_size = 1 * 1024 * 1024 * 1024
                        file_path = await async_download_youtube_audio(
                            url,
                            max_size,
                        )

                        progress_dict["is_finished"] = True

                        # =========================
                        # فایل بزرگ
                        # =========================

                        if file_path == "TOO_LARGE":
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ حجم فایل صوتی بیش از 1 گیگابایت است.",
                            )
                            await decrement_yt_downloads(chat_id)
                            return

                        # =========================

                        if (
                            file_path
                            and isinstance(file_path, str)
                            and await asyncio.to_thread(os.path.exists, file_path)
                        ):
                            # =====================
                            # cloud
                            # =====================

                            if destination == "server":
                                # =================================
                                # چک و رزرو اتمیک فضای ابری قبل از آپلود صوت
                                # =================================
                                audio_size_mb = round(
                                    (await get_file_size_async(file_path)) / (1024 * 1024), 2
                                )

                                reserved = await reserve_cloud_quota(chat_id, audio_size_mb)
                                if not reserved:
                                    user_storage_mb = await get_available_cloud_mb(chat_id)
                                    if user_storage_mb is None or user_storage_mb <= 0:
                                        user_storage_mb = 0
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

                                await _stop_updater_task(updater_task)
                                progress_dict["is_finished"] = False
                                progress_dict["text"] = "☁️ شروع آپلود ابری..."

                                updater_task = asyncio.create_task(
                                    update_progress_message()
                                )

                                try:
                                    if upload_to_s3_with_key is not None:
                                        if async_upload_to_s3_with_key is not None:
                                            s3_url, s3_key = await async_upload_to_s3_with_key(
                                                file_path,
                                                None,
                                                progress_dict,
                                                upload_fn=upload_to_s3_with_key,
                                            )
                                        else:
                                            s3_url, s3_key = await asyncio.to_thread(
                                                upload_to_s3_with_key,
                                                file_path,
                                                None,
                                                progress_dict,
                                            )
                                    else:
                                        s3_url = await asyncio.to_thread(
                                            upload_to_s3,
                                            file_path,
                                            None,
                                            progress_dict,
                                        )
                                        s3_key = None
                                except Exception:
                                    await release_cloud_quota(chat_id, audio_size_mb)
                                    raise

                                progress_dict["is_finished"] = True

                                if s3_url:
                                    file_name = os.path.basename(file_path)

                                    await record_cloud_upload(
                                        chat_id,
                                        file_name,
                                        audio_size_mb,
                                        s3_url,
                                        s3_key=s3_key,
                                        quota_reserved=True,
                                    )

                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text=f"✅ فایل صوتی با موفقیت ذخیره شد:\n\n📉 حجم کسر شده: {audio_size_mb} مگابایت\n\n🔗 [لینک دانلود]({s3_url})",
                                        parse_mode="Markdown",
                                    )

                                else:
                                    await release_cloud_quota(chat_id, audio_size_mb)
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="❌ خطا در آپلود ابری.",
                                    )

                                    await log_upload_failed("youtube", chat_id)
                                    await decrement_yt_downloads(chat_id)

                            # =====================
                            # telegram
                            # =====================

                            else:
                                file_size_mb = (await get_file_size_async(file_path)) / (
                                    1024 * 1024
                                )
                                sent_direct_audio = False

                                # Send & cache directly as audio if under 50MB (skip redundant ZIP)
                                if file_size_mb < 50:
                                    try:
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text="🎵 در حال ارسال فایل صوتی...",
                                        )

                                        audio_file_id = await upload_audio_to_storage_once(
                                            context=context,
                                            file_path=file_path,
                                            caption=f"🎵 {info.get('title') if info else video_id}",
                                        )

                                        fwd_status = await forward_file_id_to_user(
                                            context, chat_id, audio_file_id, "audio"
                                        )
                                        if fwd_status != ForwardStatus.FAILED:
                                            await save_cached_video(
                                                cache_key,
                                                [audio_file_id],
                                                title=info.get("title") if info else None,
                                                channel_name=info.get("uploader") if info else None,
                                                yt_video_id=video_id,
                                                format_type="audio",
                                                quality="best",
                                                uploaded_at=uploaded_at_from_video_info(info),
                                            )
                                            if fwd_status == ForwardStatus.OK:
                                                await context.bot.send_message(
                                                    chat_id=chat_id,
                                                    text="✅ فایل صوتی ارسال شد!",
                                                )
                                            else:
                                                await context.bot.send_message(
                                                    chat_id=chat_id,
                                                    text="⚠️ وضعیت تحویل فایل صوتی نامطمئن بود؛ پیش از درخواست مجدد چت را بررسی کنید.",
                                                )
                                            sent_direct_audio = True
                                    except Exception as audio_err:
                                        print(f"⚠️ Could not send as audio: {audio_err}")

                                if not sent_direct_audio:
                                    await context.bot.send_message(
                                        chat_id=chat_id,
                                        text="📦 در حال ساخت ZIP و تقسیم به پارت‌های 50MB...",
                                    )
                                    zip_basename = f"youtube_audio_{video_id}"
                                    (
                                        zip_parts,
                                        archive_basename,
                                        split_method,
                                    ) = await asyncio.to_thread(
                                        build_zip_and_split,
                                        file_path,
                                        os.path.dirname(file_path) or ".",
                                        zip_basename,
                                        50 * 1024 * 1024,
                                    )
                                    zip_artifacts.extend(zip_parts)
                                    if split_method == "concat":
                                        full_zip = os.path.join(
                                            os.path.dirname(file_path) or ".",
                                            f"{archive_basename}.zip",
                                        )
                                        if await asyncio.to_thread(os.path.isfile, full_zip):
                                            zip_artifacts.append(full_zip)

                                    await process_and_send_document_parts(
                                        context,
                                        chat_id,
                                        zip_parts,
                                        label=f"Audio ID: {video_id}",
                                        cache_key=cache_key,
                                        archive_basename=archive_basename,
                                        split_method=split_method,
                                        video_id=video_id,
                                        title=info.get("title") if info else None,
                                        channel_name=info.get("uploader") if info else None,
                                        uploaded_at=uploaded_at_from_video_info(info),
                                    )

                        else:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text="❌ دانلود شکست خورد.",
                            )

                            await log_upload_failed("youtube", chat_id)
                            await decrement_yt_downloads(chat_id)

                    except Exception as send_err:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"❌ خطا: {str(send_err)}",
                        )

                        await log_upload_failed("youtube", chat_id)
                        await decrement_yt_downloads(chat_id)

                    finally:
                        await remove_files_async([file_path, *zip_artifacts])

            except Exception as e:
                progress_dict["is_finished"] = True

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ خطا: {str(e)}",
                )

                await log_upload_failed("youtube", chat_id)
                await decrement_yt_downloads(chat_id)

            finally:
                await _stop_updater_task(updater_task)

    except Exception as e:
        print(f"Semaphore Error: {e}")

        await decrement_yt_downloads(chat_id)
