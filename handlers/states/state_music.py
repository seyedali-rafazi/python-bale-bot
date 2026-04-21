import os
import asyncio
import shutil
from telegram import Update
from telegram.ext import ContextTypes
from services.music import download_spotify_track, search_and_download_music


async def handle_music_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_music_search":
        await update.message.reply_text("⏳ در حال جستجو و دانلود بهترین نتیجه...")
        file_path, title = await asyncio.to_thread(
            search_and_download_music, text, chat_id
        )

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=aud, title=title
                    )
            finally:
                download_dir = f"temp_search_{chat_id}"
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir)
        else:
            await update.message.reply_text(
                "❌ متأسفانه آهنگی با این نام پیدا نشد یا خطایی رخ داد."
            )
        return

    elif step == "waiting_spotify_link":
        if "spotify.com" not in text:
            await update.message.reply_text("❌ لطفاً یک لینک معتبر اسپاتیفای بفرستید.")
            return

        await update.message.reply_text("⏳ در حال دانلود از اسپاتیفای...")
        file_path = await asyncio.to_thread(download_spotify_track, text, chat_id)

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
            await update.message.reply_text(
                "❌ دانلود شکست خورد. لطفاً لینک یک تک‌آهنگ (Track) را بفرستید."
            )
        return
