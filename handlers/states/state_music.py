# handlers/states/state_music.py

import os
import asyncio
import shutil
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.music import (
    search_spotify,
    get_album_tracks,
    get_playlist_tracks,
    get_artist_top_tracks,
    get_artist_info,
    download_spotify_track,
    get_track_info,
)


async def handle_music_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_music_track":
        results = await asyncio.to_thread(search_spotify, text, "track")
        if not results or not results["tracks"]["items"]:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results["tracks"]["items"]:
            btn_text = f"{item['name']} - {item['artists'][0]['name']}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"dltrack_{item['id']}")]
            )

        await update.message.reply_text(
            "نتایج یافت شده. برای دانلود کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif step == "waiting_music_album":
        results = await asyncio.to_thread(search_spotify, text, "album")
        if not results or not results["albums"]["items"]:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results["albums"]["items"]:
            btn_text = f"{item['name']} - {item['artists'][0]['name']}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"album_{item['id']}")]
            )

        await update.message.reply_text(
            "آلبوم‌های یافت شده:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif step == "waiting_music_artist":
        results = await asyncio.to_thread(search_spotify, text, "artist")
        if not results or not results["artists"]["items"]:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results["artists"]["items"]:
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
        results = await asyncio.to_thread(search_spotify, text, "playlist")
        if not results or not results["playlists"]["items"]:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        keyboard = []
        for item in results["playlists"]["items"]:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        item["name"], callback_data=f"playlist_{item['id']}"
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
        keyboard = [
            [InlineKeyboardButton(t["name"], callback_data=f"dltrack_{t['id']}")]
            for t in tracks["items"]
        ]
        await query.message.reply_text(
            "آهنگ‌های این آلبوم:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("playlist_"):
        playlist_id = data.split("_")[1]
        tracks = await asyncio.to_thread(get_playlist_tracks, playlist_id)
        keyboard = [
            [
                InlineKeyboardButton(
                    t["track"]["name"], callback_data=f"dltrack_{t['track']['id']}"
                )
            ]
            for t in tracks["items"]
            if t.get("track")
        ]
        await query.message.reply_text(
            "آهنگ‌های پلی‌لیست:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("artist_"):
        artist_id = data.split("_")[1]
        artist_info = await asyncio.to_thread(get_artist_info, artist_id)
        keyboard = [
            [
                InlineKeyboardButton(
                    "🎧 ۱۰ آهنگ برتر", callback_data=f"toptracks_{artist_id}"
                )
            ]
        ]

        # اگر خواننده عکس دارد ارسال کن
        if artist_info["images"]:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=artist_info["images"][0]["url"],
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await query.message.reply_text(
                f"خواننده: {artist_info['name']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data.startswith("toptracks_"):
        artist_id = data.split("_")[1]
        tracks = await asyncio.to_thread(get_artist_top_tracks, artist_id)
        keyboard = [
            [InlineKeyboardButton(t["name"], callback_data=f"dltrack_{t['id']}")]
            for t in tracks["tracks"]
        ]
        await query.message.reply_text(
            "۱۰ آهنگ برتر:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("dltrack_"):
        track_id = data.split("_")[1]
        await query.message.reply_text("⏳ در حال دانلود آهنگ...")

        track_info = await asyncio.to_thread(get_track_info, track_id)
        track_url = track_info["external_urls"]["spotify"]

        file_path = await asyncio.to_thread(download_spotify_track, track_url, chat_id)

        if file_path and os.path.exists(file_path):
            try:
                title = os.path.basename(file_path).replace(".mp3", "")
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=aud, title=title
                    )
            finally:
                download_dir = f"temp_spotify_{chat_id}"
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir)
        else:
            await query.message.reply_text("❌ دانلود شکست خورد.")
