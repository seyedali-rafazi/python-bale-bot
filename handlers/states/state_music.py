# handlers/states/state_music.py

import os
import asyncio
import shutil
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
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
            artist_name = item['artists'][0]['name'] if item.get('artists') else "ناشناس"
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
            artist_name = item['artists'][0]['name'] if item.get('artists') else "ناشناس"
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
                [
                    InlineKeyboardButton(
                        btn_text, callback_data=f"playlist_{item['id']}"
                    )
                ]
            )

        await update.message.reply_text(
            "پلی‌لیست‌های یافت شده:", reply_markup=InlineKeyboardMarkup(keyboard)
        )


# هندلر برای دریافت کال‌بک‌های دکمه‌های شیشه‌ای
async def handle_music_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = str(update.effective_chat.id)

    if data.startswith("album_"):
        album_id = data.split("_")[1]
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
        playlist_id = data.split("_")[1]
        tracks = await asyncio.to_thread(get_playlist_tracks, playlist_id)
        if not tracks:
             await query.message.reply_text("❌ آهنگی در این پلی‌لیست یافت نشد.")
             return
             
        keyboard = [
            [
                InlineKeyboardButton(
                    t["name"], callback_data=f"dltrack_{t['id']}"
                )
            ]
            for t in tracks
        ]
        await query.message.reply_text(
            "آهنگ‌های پلی‌لیست:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("artist_"):
        artist_id = data.split("_")[1]
        # برای یوتیوب موزیک مستقیماً آهنگ‌های برتر را نمایش می‌دهیم
        keyboard = [
            [
                InlineKeyboardButton(
                    "🎧 دریافت آهنگ‌های برتر خواننده", callback_data=f"toptracks_{artist_id}"
                )
            ]
        ]
        await query.message.reply_text(
            "برای دریافت آهنگ‌های برتر کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("toptracks_"):
        artist_id = data.split("_")[1]
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
        track_id = data.split("_")[1]
        await query.message.reply_text("⏳ در حال دانلود آهنگ از سرور...")

        # ساخت لینک مستقیم یوتیوب برای دانلود
        track_url = f"https://music.youtube.com/watch?v={track_id}"

        try:
            # استفاده از تابع دانلود یوتیوب (همان تابعی که برای بخش یوتیوب ربات دارید)
            file_path = await asyncio.to_thread(download_youtube_audio, track_url, chat_id)

            if file_path and os.path.exists(file_path):
                title = os.path.basename(file_path).replace(".mp3", "")
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=aud, title=title
                    )
                # حذف فایل پس از ارسال
                os.remove(file_path)
            else:
                await query.message.reply_text("❌ دانلود شکست خورد.")
        except Exception as e:
            print(f"Download Error: {e}")
            await query.message.reply_text("❌ خطایی در فرآیند دانلود رخ داد.")
