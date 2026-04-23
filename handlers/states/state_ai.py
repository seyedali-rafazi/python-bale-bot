# handlers/states/state_ai.py

import os
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state
from services.ai import ask_chatbot, generate_image, perform_ocr, text_to_speech


async def handle_ai_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_ai_chat":
        await update.message.reply_text("⏳ در حال فکر کردن...")
        answer = await asyncio.to_thread(ask_chatbot, text)
        await update.message.reply_text(answer)
        return

    elif step == "waiting_ai_tts":
        await update.message.reply_text("⏳ در حال تبدیل متن به صدا...")
        file_path = await asyncio.to_thread(text_to_speech, text, chat_id)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as aud:
                    await context.bot.send_audio(chat_id=chat_id, audio=aud)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text("❌ خطا در تولید صدا.")
        return

    elif step == "waiting_ai_image":
        await update.message.reply_text(
            "⏳ در حال تولید عکس (ممکن است کمی طول بکشد)..."
        )
        file_path = await asyncio.to_thread(generate_image, text, chat_id)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as img:
                    await context.bot.send_photo(chat_id=chat_id, photo=img)
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text(
                "❌ خطا در تولید عکس. لطفاً متن دیگری را امتحان کنید."
            )
        return


async def handle_ai_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str
):
    await update.message.reply_text("⏳ در حال دانلود و پردازش عکس...")
    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document:
            file_id = update.message.document.file_id
        else:
            await update.message.reply_text("❌ فرمت فایل پشتیبانی نمی‌شود.")
            return

        file = await context.bot.get_file(file_id)
        file_path = f"temp_ocr_{chat_id}.jpg"
        await file.download_to_drive(file_path)

        extracted_text = await asyncio.to_thread(perform_ocr, file_path)

        if os.path.exists(file_path):
            os.remove(file_path)

        await update.message.reply_text(f"✅ **متن استخراج شده:**\n\n{extracted_text}")
        set_state(chat_id, "")

    except Exception as e:
        await update.message.reply_text(f"❌ خطایی در پردازش عکس رخ داد: {e}")
        set_state(chat_id, "")
