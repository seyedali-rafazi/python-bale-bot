import os
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.instagram import download_instagram


async def handle_insta_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_ig_link":
        if "instagram.com" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return
        await update.message.reply_text("⏳ در حال دانلود از اینستاگرام...")
        file_path = await asyncio.to_thread(download_instagram, text)
        if file_path and os.path.exists(file_path):
            try:
                if file_path.endswith(".mp4"):
                    with open(file_path, "rb") as vid:
                        await context.bot.send_video(chat_id=chat_id, video=vid)
                else:
                    with open(file_path, "rb") as doc:
                        await context.bot.send_document(chat_id=chat_id, document=doc)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text("❌ دانلود شکست خورد.")
        return
