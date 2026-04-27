# handlers/states/state_music.py


import os
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

# وارد کردن توابع دیتابیس برای بررسی وضعیت کاربر و محدودیت‌ها
from core.database import is_vip, get_music_downloads, increment_music_downloads

from services.music import (
    search_track,
    search_album,
    search_artist,
    search_playlist,
    get_album_tracks,
    get_playlist_tracks,
    get_artist_top_tracks,
)

# فرض بر این است که تابع دانلود یوتیوب در این مسیر قرار دارد
from services.youtube import download_youtube_audio

# --- متغیرهای مربوط به صف ---
active_music_downloads = 0
MAX_MUSIC_CONCURRENT = 3  # حداکثر تعداد دانلود همزمان موسیقی
music_download_semaphore = asyncio.Semaphore(MAX_MUSIC_CONCURRENT)


# --- تابع پردازش در پس‌زمینه (همراه با سیستم صف) ---
async def background_download_task(
    context, chat_id, track_id, title, performer, safe_filename
):
    global active_music_downloads
    active_music_downloads += 1
    queue_pos = active_music_downloads

    # پیام اولیه صف
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ درخواست شما ثبت شد.\nشما نفر $ {queue_pos} $ در کل صف هستید.\nلطفاً تا خالی شدن ظرفیت منتظر بمانید...",
    )

    try:
        # قفل صف (تا زمانی که ظرفیت خالی شود منتظر می‌ماند)
        async with music_download_semaphore:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text="⏳ نوبت شما رسید! در حال دانلود آهنگ از سرور...",
                )
            except Exception:
                pass

            # 1. فراخوانی تابع دانلود سینک در ترد جداگانه
            file_path = await asyncio.to_thread(download_youtube_audio, track_id)

            if file_path and os.path.exists(file_path):
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text="📤 دانلود تکمیل شد! در حال آپلود فایل به بله...",
                    )
                except Exception:
                    pass

                with open(file_path, "rb") as aud:
                    # 2. ارسال فایل به کاربر
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=aud,
                        title=title,
                        performer=performer,
                        filename=f"{safe_filename}.mp3",
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=60,
                    )

                # 3. افزایش شمارنده *فقط* بعد از آپلود و ارسال موفق
                increment_music_downloads(chat_id)

                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text="✅ آهنگ با موفقیت ارسال شد!",
                    )
                except Exception:
                    pass

                # 4. حذف فایل از سرور
                os.remove(file_path)
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
        active_music_downloads -= 1


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

    elif data.startswith("dltrack_"):
        track_id = data.split("_", 1)[1]

        # 1. بررسی محدودیت کاربر
        user_vip_status = is_vip(chat_id)
        limit = 20 if user_vip_status else 6
        current_downloads = get_music_downloads(chat_id)

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

        # 2. ایجاد تسک در پس‌زمینه (عملیات اصلی شامل صف و پیام‌ها در این تابع انجام می‌شود)
        asyncio.create_task(
            background_download_task(
                context, chat_id, track_id, title, performer, safe_filename
            )
        )
