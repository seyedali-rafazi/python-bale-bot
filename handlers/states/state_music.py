# handlers/states/state_music.py


import os
import asyncio
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
)
from services.music import (
    search_track,
    search_album,
    search_artist,
    search_playlist,
    get_album_tracks,
    get_playlist_tracks,
    get_artist_top_tracks,
)
from services.youtube import download_youtube_audio

try:
    from services.parspack_s3 import upload_to_s3
except ImportError:
    upload_to_s3 = None

# صف دانلود برای جلوگیری از فشار به سرور و محدودیت‌های یوتیوب
MAX_MUSIC_CONCURRENT = 3
music_download_semaphore = asyncio.Semaphore(MAX_MUSIC_CONCURRENT)


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
        # قفل صف (فقط 3 دانلود همزمان انجام می‌شود)
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

                    # ثبت آمار پس از موفقیت (اصلاح شد: اضافه شدن await)
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

    except Exception as e:
        print(f"Download/Upload Error: {e}")
        await context.bot.send_message(
            chat_id, "❌ خطایی در فرآیند دانلود یا ارسال رخ داد."
        )

    finally:
        # تضمین پاک شدن فایل از روی هارد سرور در هر شرایطی (حتی در صورت کرش یا قطعی اینترنت)
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to remove file {file_path}: {e}")


# ----------------------------------------------------------------


async def handle_music_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_music_track":
        results = await asyncio.to_thread(search_track, text)
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
        results = await asyncio.to_thread(search_album, text)
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
        results = await asyncio.to_thread(search_artist, text)
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
        results = await asyncio.to_thread(search_playlist, text)
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
        tracks = await asyncio.to_thread(get_album_tracks, album_id)
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
        tracks = await asyncio.to_thread(get_playlist_tracks, playlist_id)
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
        tracks = await asyncio.to_thread(get_artist_top_tracks, artist_id)
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
    elif data.startswith("dltrack_tel_"):
        track_id = data.split("_", 3)[2]
        track_info = context.user_data.get(f"track_{track_id}", {})

        asyncio.create_task(
            background_download_task(
                context,
                chat_id,
                track_id,
                track_info.get("title", "Unknown"),
                track_info.get("performer", "Unknown"),
                track_info.get("safe_filename", "track"),
                destination="telegram",
            )
        )

    elif data.startswith("dltrack_cloud_"):
        track_id = data.split("_", 3)[2]
        track_info = context.user_data.get(f"track_{track_id}", {})

        asyncio.create_task(
            background_download_task(
                context,
                chat_id,
                track_id,
                track_info.get("title", "Unknown"),
                track_info.get("performer", "Unknown"),
                track_info.get("safe_filename", "track"),
                destination="server",
            )
        )

    # ===================================
    # کال‌بک دانلود عام (انتخاب مقصد)
    # ===================================
    elif data.startswith("dltrack_"):
        track_id = data.split("_", 1)[1]

        # 1. بررسی محدودیت کاربر (اصلاح شد: اضافه شدن await)
        user_vip_status = await is_vip(chat_id)
        limit = 20 if user_vip_status else 6
        current_downloads = await get_music_downloads(chat_id)

        if current_downloads >= limit:
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

        # ذخیره اطلاعات برای استفاده بعدی
        context.user_data[f"track_{track_id}"] = {
            "title": title,
            "performer": performer,
            "safe_filename": safe_filename,
        }
