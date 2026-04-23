import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.translator import translate_text


async def handle_translation_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_tr_fa_en":
        await update.message.reply_text("⏳ در حال ترجمه به انگلیسی...")
        # فراخوانی سرویس ترجمه
        result = await asyncio.to_thread(translate_text, "fa", "en", text)
        await update.message.reply_text(f"✅ **نتیجه ترجمه:**\n\n{result}")
        return

    elif step == "waiting_tr_en_fa":
        await update.message.reply_text("⏳ در حال ترجمه به فارسی...")
        # فراخوانی سرویس ترجمه
        result = await asyncio.to_thread(translate_text, "en", "fa", text)
        await update.message.reply_text(f"✅ **نتیجه ترجمه:**\n\n{result}")
        return
