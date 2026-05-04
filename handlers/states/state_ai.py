# handlers/states/state_ai.py

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state
from services.ai import ask_chatbot, generate_image, perform_ocr, text_to_speech

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
                # فراخوانی مستقیم تابع Async
                answer = await ask_chatbot(text)
            await msg.edit_text(answer)

        elif step == "waiting_ai_tts":
            msg = await update.message.reply_text("⏳ در حال تبدیل متن به صدا...")
            async with ai_media_semaphore:
                audio_fp = await text_to_speech(text)

            if audio_fp:
                # ارسال مستقیم از حافظه رم
                await context.bot.send_audio(chat_id=chat_id, audio=audio_fp)
                await msg.delete()
            else:
                await msg.edit_text("❌ خطا در تولید صدا.")

        elif step == "waiting_ai_image":
            msg = await update.message.reply_text(
                "⏳ در حال تولید عکس (ممکن است طول بکشد)..."
            )
            async with ai_media_semaphore:
                img_fp = await generate_image(text)

            if img_fp:
                await context.bot.send_photo(chat_id=chat_id, photo=img_fp)
                await msg.delete()
            else:
                await msg.edit_text(
                    "❌ خطا در تولید عکس. لطفاً متن دیگری را امتحان کنید."
                )

    except Exception as e:
        print(f"AI State Error: {e}")
        await update.message.reply_text("❌ خطای سیستمی در پردازش درخواست شما رخ داد.")
    finally:
        set_state(chat_id, "")


async def handle_ai_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str
):
    msg = await update.message.reply_text("⏳ در حال دریافت و پردازش عکس...")
    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document:
            file_id = update.message.document.file_id
        else:
            await msg.edit_text("❌ فرمت فایل پشتیبانی نمی‌شود.")
            return

        # دانلود فایل به صورت آرایه بایت در رم (بدون دخالت هارد دیسک)
        file = await context.bot.get_file(file_id)
        image_byte_array = await file.download_as_bytearray()
        image_bytes = bytes(image_byte_array)

        async with ai_media_semaphore:
            extracted_text = await perform_ocr(image_bytes)

        await msg.edit_text(
            f"✅ **متن استخراج شده:**\n\n{extracted_text}", parse_mode="Markdown"
        )

    except Exception as e:
        print(f"OCR Handler Error: {e}")
        await msg.edit_text(f"❌ خطایی در پردازش عکس رخ داد.")
    finally:
        set_state(chat_id, "")
