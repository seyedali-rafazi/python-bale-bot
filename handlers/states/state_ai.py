# handlers/states/state_ai.py


import asyncio
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.task_utils import track_task
from core.database import can_user_ask_ai, increment_ai_question, log_upload_success

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

MAX_AI_CHAT_QUEUE = max(3, int(os.getenv("MAX_AI_CHAT_QUEUE", "8")))
ai_chat_semaphore = asyncio.Semaphore(MAX_AI_CHAT_QUEUE)
_ai_chat_in_flight = 0

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
    global _ai_chat_in_flight
    try:
        async with ai_chat_semaphore:
            answer = await ask_chatbot(text)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=answer[:4096],
        )
        await log_upload_success("ai_chat", chat_id)

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
    finally:
        _ai_chat_in_flight = max(0, _ai_chat_in_flight - 1)


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
        await log_upload_success("ai_chat", chat_id)

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
        await log_upload_success("ai_chat", chat_id)

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
            if not (text and text.strip()):
                await update.message.reply_text(
                    "❌ دستیار هوشمند فقط **متن** می‌پذیرد.\n"
                    "عکس، صدا، ویدیو و فایل پشتیبانی نمی‌شود.",
                    parse_mode="Markdown",
                )
                return

            allowed, used, limit = await can_user_ask_ai(chat_id)
            if not allowed:
                await update.message.reply_text(
                    f"❌ سقف پرسش روزانه شما تمام شده است.\n\n"
                    f"📊 امروز: {used} از {limit} پرسش\n"
                    f"🔄 ریست: نیمه‌شب به وقت تهران\n"
                    f"🌟 با اشتراک Pro تا {20} پرسش در روز دریافت کنید."
                )
                return

            global _ai_chat_in_flight
            if _ai_chat_in_flight >= MAX_AI_CHAT_QUEUE:
                await update.message.reply_text(
                    "⏳ صف دستیار هوشمند در حال حاضر شلوغ است. لطفاً چند ثانیه دیگر دوباره تلاش کنید."
                )
                return

            await increment_ai_question(chat_id)
            _ai_chat_in_flight += 1

            msg = await update.message.reply_text(
                "⏳ درخواست شما در صف پردازش قرار گرفت..."
            )

            track_task(
                process_ai_chat(
                    context=context,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=text,
                ),
                name=f"ai_chat_{chat_id}",
            )

            return

        # -------------------------------------------------
        # TTS
        # -------------------------------------------------

        elif step == "waiting_ai_tts":
            msg = await update.message.reply_text("⏳ در حال تولید صدا...")

            track_task(
                process_ai_tts(
                    context=context,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=text,
                ),
                name=f"ai_tts_{chat_id}",
            )

            return

        # -------------------------------------------------
        # IMAGE
        # -------------------------------------------------

        elif step == "waiting_ai_image":
            msg = await update.message.reply_text("⏳ در حال تولید تصویر...")

            track_task(
                process_ai_image(
                    context=context,
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=text,
                ),
                name=f"ai_image_{chat_id}",
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
        await log_upload_success("ai_chat", chat_id)

    except Exception:
        logger.exception("handle_ai_photo failed")

        await msg.edit_text("❌ خطا در پردازش تصویر")

    finally:
        set_state(chat_id, "")
