# handlers/states/state_ai.py

import os
import asyncio
import uuid
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state
from services.ai import ask_chatbot, generate_image, perform_ocr, text_to_speech

# محدودکننده‌های ترافیک برای جلوگیری از مسدود شدن APIها
ai_text_semaphore = asyncio.Semaphore(15)
ai_media_semaphore = asyncio.Semaphore(5)


async def handle_ai_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    try:
        if step == "waiting_ai_chat":
            msg = await update.message.reply_text("⏳ در حال پردازش...")
            async with ai_text_semaphore:
                answer = await asyncio.to_thread(ask_chatbot, text)
            # ویرایش پیام قبلی به جای ارسال پیام جدید برای خلوت ماندن چت
            await msg.edit_text(answer)

        elif step == "waiting_ai_tts":
            msg = await update.message.reply_text("⏳ در حال تبدیل متن به صدا...")
            unique_id = uuid.uuid4().hex
            async with ai_media_semaphore:
                file_path = await asyncio.to_thread(text_to_speech, text, unique_id)

            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as aud:
                        await context.bot.send_audio(chat_id=chat_id, audio=aud)
                    await msg.delete()
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                await msg.edit_text("❌ خطا در تولید صدا.")

        elif step == "waiting_ai_image":
            msg = await update.message.reply_text(
                "⏳ در حال تولید عکس (ممکن است طول بکشد)..."
            )
            unique_id = uuid.uuid4().hex
            async with ai_media_semaphore:
                file_path = await asyncio.to_thread(generate_image, text, unique_id)

            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as img:
                        await context.bot.send_photo(chat_id=chat_id, photo=img)
                    await msg.delete()
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                await msg.edit_text(
                    "❌ خطا در تولید عکس. لطفاً متن دیگری را امتحان کنید."
                )

    except Exception as e:
        print(f"AI State Error: {e}")
        await update.message.reply_text("❌ خطای سیستمی در پردازش درخواست شما رخ داد.")
    finally:
        # بسیار مهم: همیشه وضعیت کاربر را در نهایت پاک کنید
        set_state(chat_id, "")


async def handle_ai_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str
):
    msg = await update.message.reply_text("⏳ در حال دانلود و پردازش عکس...")
    file_path = None
    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document:
            file_id = update.message.document.file_id
        else:
            await msg.edit_text("❌ فرمت فایل پشتیبانی نمی‌شود.")
            return

        unique_id = uuid.uuid4().hex
        file_path = f"temp_ocr_{unique_id}.jpg"

        file = await context.bot.get_file(file_id)
        await file.download_to_drive(file_path)

        async with ai_media_semaphore:
            extracted_text = await asyncio.to_thread(perform_ocr, file_path)

        await msg.edit_text(
            f"✅ **متن استخراج شده:**\n\n{extracted_text}", parse_mode="Markdown"
        )

    except Exception as e:
        print(f"OCR Handler Error: {e}")
        await msg.edit_text(f"❌ خطایی در پردازش عکس رخ داد.")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        set_state(chat_id, "")
