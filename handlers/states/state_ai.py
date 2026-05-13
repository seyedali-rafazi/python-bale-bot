# handlers/states/state_ai.py

# handlers/states/state_ai.py

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state

from services.ai import (
    ask_chatbot,
    perform_ocr,
    generate_image,
    text_to_speech,
)

logger = logging.getLogger(__name__)

# =========================================================
# LIMITERS
# =========================================================

ai_chat_semaphore = asyncio.Semaphore(10)

ai_media_semaphore = asyncio.Semaphore(5)

# =========================================================
# BACKGROUND AI CHAT
# =========================================================


async def process_ai_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    message_id: int,
    text: str,
):

    try:
        async with ai_chat_semaphore:
            answer = await ask_chatbot(text)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=answer[:4096],
        )

    except Exception:
        logger.exception("process_ai_chat failed")

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ خطا در پردازش AI",
            )

        except Exception:
            pass


# =========================================================
# BACKGROUND TTS
# =========================================================


async def process_ai_tts(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    message_id: int,
    text: str,
):

    try:
        async with ai_media_semaphore:
            audio_fp = await text_to_speech(text)

        if not audio_fp:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ خطا در تولید صدا",
            )

            return

        await context.bot.send_audio(
            chat_id=chat_id,
            audio=audio_fp,
        )

        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )

    except Exception:
        logger.exception("process_ai_tts failed")

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ خطا در تولید صدا",
            )
        except Exception:
            pass


# =========================================================
# BACKGROUND IMAGE
# =========================================================


async def process_ai_image(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    message_id: int,
    text: str,
):

    try:
        async with ai_media_semaphore:
            img_fp = await generate_image(text)

        if not img_fp:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ خطا در تولید عکس",
            )

            return

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=img_fp,
        )

        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )

    except Exception:
        logger.exception("process_ai_image failed")

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ خطا در تولید عکس",
            )
        except Exception:
            pass


# =========================================================
# MAIN AI STATE
# =========================================================


async def handle_ai_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):

    try:
        # -------------------------------------------------
        # CHAT
        # -------------------------------------------------

        if step == "waiting_ai_chat":
            msg = await update.message.reply_text(
                "⏳ درخواست شما در صف پردازش قرار گرفت..."
            )

            context.application.create_task(
                process_ai_chat(
                    context=context,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=text,
                )
            )

            return

        # -------------------------------------------------
        # TTS
        # -------------------------------------------------

        elif step == "waiting_ai_tts":
            msg = await update.message.reply_text("⏳ در حال تولید صدا...")

            context.application.create_task(
                process_ai_tts(
                    context=context,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=text,
                )
            )

            return

        # -------------------------------------------------
        # IMAGE
        # -------------------------------------------------

        elif step == "waiting_ai_image":
            msg = await update.message.reply_text("⏳ در حال تولید تصویر...")

            context.application.create_task(
                process_ai_image(
                    context=context,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=text,
                )
            )

            return

    except Exception:
        logger.exception("handle_ai_state failed")

        await update.message.reply_text("❌ خطای سیستمی")

    finally:
        set_state(chat_id, "")


# =========================================================
# OCR
# =========================================================


async def handle_ai_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
):

    msg = await update.message.reply_text("⏳ در حال پردازش تصویر...")

    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id

        elif update.message.document:
            file_id = update.message.document.file_id

        else:
            await msg.edit_text("❌ فایل پشتیبانی نمی‌شود.")

            return

        file = await context.bot.get_file(file_id)

        image_byte_array = await file.download_as_bytearray()

        image_bytes = bytes(image_byte_array)

        async with ai_media_semaphore:
            extracted_text = await perform_ocr(image_bytes)

        await msg.edit_text(f"✅ متن استخراج شده:\n\n{extracted_text}")

    except Exception:
        logger.exception("handle_ai_photo failed")

        await msg.edit_text("❌ خطا در پردازش تصویر")

    finally:
        set_state(chat_id, "")
