# handlers/states/state_insta.py

from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import clear_state
from core.keyboards import get_main_menu_keyboard
from services.instagram import download_instagram_post, get_latest_post
import os


async def handle_insta_state(
    update: Update, context: ContextTypes.DEFAULT_TYPE, step, text, chat_id, state_data
):

    await update.message.reply_text("⏳ در حال دانلود...")

    if step == "waiting_ig_link":
        result = download_instagram_post(text)

    elif step == "waiting_ig_last_post":
        result = get_latest_post(text)

    else:
        # اگر استپ تعریف نشده بود، از تابع خارج شو
        clear_state(chat_id)
        await update.message.reply_text(
            "خطای داخلی: وضعیت نامشخص.", reply_markup=get_main_menu_keyboard()
        )
        return

    if not result["success"]:
        error_message = result.get("error", "خطا در دانلود")
        await update.message.reply_text(f"❌ {error_message}")
        clear_state(chat_id)
        return

    file_path = result["file"]
    caption = result.get("caption", "")

    try:
        # بررسی می‌کنیم که فایل ویدئویی است یا عکس
        if file_path.lower().endswith((".mp4", ".mov", ".avi")):
            await update.message.reply_video(
                video=open(file_path, "rb"),
                caption=caption[:1024],  # محدودیت کپشن ویدئو بیشتر است
            )
        else:  # برای بقیه فرمت‌ها مثل jpg, png, webp و...
            await update.message.reply_photo(
                photo=open(file_path, "rb"), caption=caption[:1024]
            )

    except Exception as e:
        await update.message.reply_text(f"خطا در ارسال فایل: {e}")

    finally:
        # پاک کردن فایل دانلود شده برای جلوگیری از پر شدن حافظه
        if os.path.exists(file_path):
            os.remove(file_path)

        clear_state(chat_id)

        await update.message.reply_text(
            "✅ انجام شد", reply_markup=get_main_menu_keyboard()
        )
