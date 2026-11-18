# handlers/states/state_music.py


import os
import asyncio
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from core.database import (
    is_vip,
    get_music_downloads,
    increment_music_downloads,
    get_available_cloud_mb,
    reduce_cloud_storage,
    add_cloud_file,
    log_upload_success,
    log_upload_failed,
)
from core.state_manager import StateCache
from core.limits import get_limit
from core.task_utils import remove_file_async, track_task
from services.rate_limiter import user_action_lock
from services.music import (
    async_search_track,
    async_search_album,
    search_artist,
    async_search_playlist,
    async_get_album_tracks,
    async_get_playlist_tracks,
    async_get_artist_top_tracks,
)
from services.music_identify import (
    IDENTIFY_DIR,
    MAX_DURATION_SEC,
    async_extract_audio_to_mp3,
    format_duration_fa,
    format_identified_info_message,
    get_api_duration_sec,
    get_message_media,
    async_probe_media_duration_sec,
    recognize_music_from_file,
)
from services.youtube import download_youtube_audio

try:
    from services.parspack_s3 import upload_to_s3
except ImportError:
    upload_to_s3 = None

# صف دانلود برای جلوگیری از فشار به سرور و محدودیت‌های یوتیوب
MAX_MUSIC_CONCURRENT = 3
music_download_semaphore = asyncio.Semaphore(MAX_MUSIC_CONCURRENT)
_music_track_cache = StateCache(max_capacity=2000, default_ttl=3600.0)


async def background_download_task(
    context,
    chat_id,
    track_id,
    title,
    performer,
    safe_filename,
    destination: str = "telegram",
):
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ درخواست شما در صف دانلود قرار گرفت.\nلطفاً شکیبا باشید...",
    )

    file_path = None  # برای استفاده در بلاک finally

    try:
        # قفل صف فقط برای مرحله دانلود (آپلود به بله/S3 سمافور دانلود را اشغال نمی‌کند)
        async with music_download_semaphore:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text="⏳ نوبت شما رسید! در حال دانلود...",
                )
            except BadRequest:
                pass

            # دانلود در ترد جداگانه
            file_path = await asyncio.to_thread(download_youtube_audio, track_id)

        if file_path and os.path.exists(file_path):
                # =====================================
                # چک فضای ابری برای آپلود به سرور
                # =====================================
                if destination == "server":
                    user_storage_mb = await get_available_cloud_mb(chat_id)
                    if user_storage_mb is None or user_storage_mb <= 0:
                        user_storage_mb = 0

                    file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)

                    if user_storage_mb <= 0 or file_size_mb > user_storage_mb:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"❌ فضای ابری شما کافی نیست!\n\n"
                                f"حجم فایل صوتی: {file_size_mb} مگابایت\n"
                                f"فضای باقیمانده شما: {round(user_storage_mb, 2)} مگابایت\n\n"
                                f"لطفاً برای ارتقای حجم ابری خود از طریق منوی فروشگاه اقدام کنید."
                            ),
                        )
                        return

                # =====================================

                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text="📤 دانلود تکمیل شد! در حال آپلود...",
                    )
                except BadRequest:
                    pass

                # ========================
                # آپلود به سرور ابری
                # ========================
                if destination == "server":
                    progress_dict = {"text": "شروع آپلود ابری...", "is_finished": False}

                    s3_url = await asyncio.to_thread(
                        upload_to_s3,
                        file_path,
                        None,
                        progress_dict,
                    )

                    if s3_url:
                        file_size_mb = round(
                            os.path.getsize(file_path) / (1024 * 1024), 2
                        )
                        file_name = os.path.basename(file_path)

                        await add_cloud_file(chat_id, file_name, file_size_mb, s3_url)
                        await reduce_cloud_storage(chat_id, file_size_mb)

                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ آهنگ با موفقیت در فضای ابری ذخیره شد:\n\n📉 حجم کسر شده: {file_size_mb} مگابایت\n\n🔗 [لینک دانلود]({s3_url})",
                            parse_mode="Markdown",
                        )

                        await increment_music_downloads(chat_id)
                        return

                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="❌ خطا در آپلود ابری.",
                        )
                        await log_upload_failed("music", chat_id)
                        return

                # ========================
                # آپلود به بله
                # ========================
                else:
                    # ارسال فایل به صورت مستقیم بدون with open (ارسال ناهمگام و بدون فریز)
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=file_path,
                        title=title,
                        performer=performer,
                        filename=f"{safe_filename}.mp3",
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=60,
                    )

                    # ثبت آمار پس از موفقیت
                    await increment_music_downloads(chat_id)

                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text="✅ آهنگ با موفقیت ارسال شد!",
                        )
                    except BadRequest:
                        pass
        else:
                await context.bot.send_message(
                    chat_id, "❌ دانلود از سرور مبدا شکست خورد یا فایل یافت نشد."
                )
                await log_upload_failed("music", chat_id)

    except Exception as e:
        print(f"Download/Upload Error: {e}")
        await context.bot.send_message(
            chat_id, "❌ خطایی در فرآیند دانلود یا ارسال رخ داد."
        )
        await log_upload_failed("music", chat_id)

    finally:
        # تضمین پاک شدن فایل از روی هارد سرور در هر شرایطی (حتی در صورت کرش یا قطعی اینترنت)
        await remove_file_async(file_path)


# ----------------------------------------------------------------


def _make_safe_filename(title: str, performer: str) -> str:
    label = f"{title} - {performer}"
    return "".join(c for c in label if c.isalnum() or c in " -_").strip() or "track"


async def _can_download_music(chat_id: str) -> tuple[bool, int]:
    user_vip_status, current_downloads = await asyncio.gather(
        is_vip(chat_id),
        get_music_downloads(chat_id),
    )
    limit = get_limit("music_download", int(bool(user_vip_status)))
    return current_downloads < limit, limit


async def handle_music_identify_media(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = str(update.effective_chat.id)
    media = get_message_media(update.message)
    if not media:
        await update.message.reply_text(
            "❌ لطفاً ویس، فایل صوتی یا ویدیو (حداکثر ۳ دقیقه) ارسال کنید."
        )
        return

    file_obj, filename = media
    api_duration = get_api_duration_sec(file_obj)
    if api_duration is not None and api_duration > MAX_DURATION_SEC:
        await update.message.reply_text(
            f"❌ حداکثر مدت مجاز ۳ دقیقه است. مدت فایل شما: {format_duration_fa(api_duration)}."
        )
        return

    status_msg = await update.message.reply_text("🔎 در حال تشخیص آهنگ...")

    req_id = uuid.uuid4().hex[:8]
    raw_path = os.path.join(IDENTIFY_DIR, f"{chat_id}_{req_id}_{filename}")
    audio_path = os.path.join(IDENTIFY_DIR, f"{chat_id}_{req_id}_identify.mp3")
    paths_to_remove = []

    try:
        tg_file = await context.bot.get_file(file_obj.file_id)
        await tg_file.download_to_drive(raw_path)
        paths_to_remove.append(raw_path)

        real_duration = await async_probe_media_duration_sec(raw_path)
        if real_duration is not None and real_duration > MAX_DURATION_SEC:
            await status_msg.edit_text(
                f"❌ حداکثر مدت مجاز ۳ دقیقه است. مدت فایل شما: {format_duration_fa(real_duration)}."
            )
            return

        is_video = (
            update.message.video is not None
            or update.message.video_note is not None
            or (
                update.message.document
                and (update.message.document.mime_type or "").startswith("video/")
            )
        )

        recognize_path = raw_path
        if is_video or not raw_path.lower().endswith((".mp3", ".ogg", ".m4a", ".wav")):
            ok = await async_extract_audio_to_mp3(
                raw_path, audio_path, MAX_DURATION_SEC
            )
            if not ok:
                await status_msg.edit_text("❌ استخراج صدا از فایل ناموفق بود.")
                return
            recognize_path = audio_path
            paths_to_remove.append(audio_path)

        identified = await recognize_music_from_file(recognize_path)
        if not identified:
            await status_msg.edit_text(
                "❌ آهنگی شناسایی نشد.\n"
                "لطفاً بخش واضح‌تری از آهنگ (بدون نویز زیاد) ارسال کنید."
            )
            return

        query = f"{identified['title']} {identified['artist']}".strip()
        results = await async_search_track(query, 5)

        try:
            await status_msg.delete()
        except BadRequest:
            pass

        if not results:
            await update.message.reply_text(
                format_identified_info_message(identified, pending_download=False)
                + "\n\n❌ اما نتیجه‌ای برای دانلود در یوتیوب موزیک پیدا نشد."
            )
            return

        await update.message.reply_text(format_identified_info_message(identified))

        can_download, limit = await _can_download_music(chat_id)
        if not can_download:
            await update.message.reply_text(
                f"❌ محدودیت دانلود روزانه شما به پایان رسیده است ({limit} آهنگ).\n"
                "فردا مجدداً تلاش کنید."
            )
            return

        best = results[0]
        track_id = best["id"]
        dl_title = best["name"]
        dl_performer = (
            best["artists"][0]["name"] if best.get("artists") else identified["artist"]
        )
        safe_filename = _make_safe_filename(dl_title, dl_performer)

        track_task(
            background_download_task(
                context,
                chat_id,
                track_id,
                dl_title,
                dl_performer,
                safe_filename,
                destination="telegram",
            ),
            name=f"music_identify_dl_{chat_id}",
        )

    except Exception as e:
        print(f"Music identify error: {e}")
        try:
            await status_msg.edit_text("❌ خطایی در تشخیص آهنگ رخ داد.")
        except BadRequest:
            await update.message.reply_text("❌ خطایی در تشخیص آهنگ رخ داد.")

    finally:
        for path in paths_to_remove:
            await remove_file_async(path)


async def handle_music_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_music_track":
        results = await async_search_track(text)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results:
            artist_name = (
                item["artists"][0]["name"] if item.get("artists") else "ناشناس"
            )
            btn_text = f"{item['name']} - {artist_name}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"dltrack_{item['id']}")]
            )

        await update.message.reply_text(
            "نتایج یافت شده. برای دانلود کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif step == "waiting_music_album":
        results = await async_search_album(text)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results:
            artist_name = (
                item["artists"][0]["name"] if item.get("artists") else "ناشناس"
            )
            btn_text = f"{item['name']} - {artist_name}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"album_{item['id']}")]
            )

        await update.message.reply_text(
            "آلبوم‌های یافت شده:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif step == "waiting_music_artist":
        results = search_artist(text)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        item["name"], callback_data=f"artist_{item['id']}"
                    )
                ]
            )

        await update.message.reply_text(
            "خواننده‌های یافت شده:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif step == "waiting_music_playlist":
        results = await async_search_playlist(text)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results:
            btn_text = f"{item['name']} (ایجاد کننده: {item.get('owner', 'ناشناس')})"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"playlist_{item['id']}")]
            )

        await update.message.reply_text(
            "پلی‌لیست‌های یافت شده:", reply_markup=InlineKeyboardMarkup(keyboard)
        )


# هندلر برای دریافت کال‌بک‌های دکمه‌های شیشه‌ای
async def handle_music_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # جلوگیری از کرش ربات در صورت قطعی یا کندی سرور بله
    try:
        await query.answer()
    except Exception as e:
        print(f"Query answer error (Ignored): {e}")

    data = query.data
    chat_id = str(update.effective_chat.id)

    if data.startswith("album_"):
        album_id = data.split("_", 1)[1]
        tracks = await async_get_album_tracks(album_id)
        if not tracks:
            await query.message.reply_text("❌ آهنگی در این آلبوم یافت نشد.")
            return

        keyboard = [
            [InlineKeyboardButton(t["name"], callback_data=f"dltrack_{t['id']}")]
            for t in tracks
        ]
        await query.message.reply_text(
            "آهنگ‌های این آلبوم:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("playlist_"):
        playlist_id = data.split("_", 1)[1]
        tracks = await async_get_playlist_tracks(playlist_id)
        if not tracks:
            await query.message.reply_text("❌ آهنگی در این پلی‌لیست یافت نشد.")
            return

        keyboard = [
            [InlineKeyboardButton(t["name"], callback_data=f"dltrack_{t['id']}")]
            for t in tracks
        ]
        await query.message.reply_text(
            "آهنگ‌های پلی‌لیست:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("artist_"):
        artist_id = data.split("_", 1)[1]
        keyboard = [
            [
                InlineKeyboardButton(
                    "🎧 دریافت آهنگ‌های برتر خواننده",
                    callback_data=f"toptracks_{artist_id}",
                )
            ]
        ]
        await query.message.reply_text(
            "برای دریافت آهنگ‌های برتر کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("toptracks_"):
        artist_id = data.split("_", 1)[1]
        tracks = await async_get_artist_top_tracks(artist_id)
        if not tracks:
            await query.message.reply_text("❌ آهنگی برای این خواننده یافت نشد.")
            return

        keyboard = [
            [InlineKeyboardButton(t["name"], callback_data=f"dltrack_{t['id']}")]
            for t in tracks
        ]
        await query.message.reply_text(
            "آهنگ‌های برتر:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ===================================
    # بررسی کال‌بک‌های دانلود به بله و ابری (قبل از dltrack_ عام)
    # ===================================
    elif data.startswith("dltrack_tel_") or data.startswith("dltrack_cloud_"):
        is_cloud = data.startswith("dltrack_cloud_")
        track_id = data.split("_", 3)[2]
        destination = "server" if is_cloud else "telegram"

        async with user_action_lock(chat_id, "music_dl", timeout_sec=10) as acquired:
            if not acquired:
                await query.message.reply_text("⏳ درخواست شما در حال ثبت است. لطفاً صبر کنید.")
                return

            can_download, limit = await _can_download_music(chat_id)
            if not can_download:
                await query.message.reply_text(
                    f"❌ محدودیت دانلود روزانه شما به پایان رسیده است ($ {limit} $ آهنگ).\nفردا مجدداً تلاش کنید."
                )
                return

            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass

            track_info = (
                _music_track_cache.pop(f"{chat_id}:{track_id}", None)
                or context.user_data.pop(f"track_{track_id}", None)
                or {}
            )

            track_task(
                background_download_task(
                    context,
                    chat_id,
                    track_id,
                    track_info.get("title", "Unknown"),
                    track_info.get("performer", "Unknown"),
                    track_info.get("safe_filename", "track"),
                    destination=destination,
                ),
                name=f"music_dl_{'cloud' if is_cloud else 'tel'}_{chat_id}",
            )

    # ===================================
    # کال‌بک دانلود عام (انتخاب مقصد)
    # ===================================
    elif data.startswith("dltrack_"):
        track_id = data.split("_", 1)[1]

        can_download, limit = await _can_download_music(chat_id)
        if not can_download:
            await query.message.reply_text(
                f"❌ محدودیت دانلود روزانه شما به پایان رسیده است ($ {limit} $ آهنگ).\nفردا مجدداً تلاش کنید."
            )
            return

        # پیدا کردن متن دکمه‌ای که کاربر روی آن کلیک کرده برای استخراج نام و خواننده
        button_text = "Unknown Track"
        if query.message.reply_markup and query.message.reply_markup.inline_keyboard:
            for row in query.message.reply_markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data == data:
                        button_text = btn.text
                        break

        # جدا کردن نام آهنگ و خواننده
        title = button_text
        performer = "YouTube Music"

        if " - " in button_text:
            try:
                parts = button_text.split(" - ", 1)
                title = parts[0].strip()
                performer = parts[1].strip()
            except ValueError:
                pass

        # تمیز کردن نام فایل برای جلوگیری از خطای بله
        safe_filename = "".join(
            c for c in button_text if c.isalnum() or c in " -_"
        ).strip()

        # ===================================
        # نمایش گزینه‌های مقصد
        # ===================================
        keyboard = [
            [
                InlineKeyboardButton(
                    "📱 بله", callback_data=f"dltrack_tel_{track_id}"
                ),
                InlineKeyboardButton(
                    "☁️ فضای ابری", callback_data=f"dltrack_cloud_{track_id}"
                ),
            ]
        ]

        await query.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        # ذخیره اطلاعات در کش محدود با TTL (جلوگیری از رشد بی‌حد context.user_data)
        _music_track_cache[f"{chat_id}:{track_id}"] = {
            "title": title,
            "performer": performer,
            "safe_filename": safe_filename,
        }
