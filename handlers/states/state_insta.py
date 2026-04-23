# handlers/states/state_insta.py

from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import clear_state
from core.keyboards import get_main_menu_keyboard
from services.instagram import download_instagram_post, download_latest_post
import os


async def handle_insta_state(
    update: Update, context: ContextTypes.DEFAULT_TYPE, step, text, chat_id, state_data
):

    await update.message.reply_text("⏳ در حال دانلود...")

    if step == "waiting_ig_link":
        result = download_instagram_post(text)

    elif step == "waiting_ig_last_post":
        result = download_latest_post(text)

    else:
        return

    if not result["success"]:
        await update.message.reply_text("❌ خطا در دانلود")
        clear_state(chat_id)
        return

    file_path = result["file"]
    caption = result.get("caption", "")

    try:
        if file_path.endswith(".mp4"):
            await update.message.reply_video(
                video=open(file_path, "rb"), caption=caption[:800]
            )

        else:
            await update.message.reply_photo(
                photo=open(file_path, "rb"), caption=caption[:800]
            )

    except Exception as e:
        await update.message.reply_text(f"خطا در ارسال فایل: {e}")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

        clear_state(chat_id)

        await update.message.reply_text(
            "✅ انجام شد", reply_markup=get_main_menu_keyboard()
        )
