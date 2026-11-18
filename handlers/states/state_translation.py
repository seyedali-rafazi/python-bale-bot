# handlers/states/state_translation.py

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.translator import async_translate_text
from core.state_manager import clear_state
from core.database import log_upload_success
from handlers.utils import escape_markdown, safe_edit_or_reply

# محدودکننده برای جلوگیری از بلاک شدن آی‌پی توسط گوگل (حداکثر 10 ترجمه همزمان)
TRANSLATION_SEMAPHORE = asyncio.Semaphore(10)


async def handle_translation_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    wait_msg = None
    try:
        if step == "waiting_tr_fa_en":
            source, target = "fa", "en"
        elif step == "waiting_tr_en_fa":
            source, target = "en", "fa"
        else:
            return

        # ارسال پیام انتظار
        wait_msg = await update.message.reply_text("⏳ در حال ترجمه...")

        async with TRANSLATION_SEMAPHORE:
            result = await async_translate_text(source, target, text)

        # ویرایش پیام انتظار به جای ارسال یک پیام جدید (UX بهتر)
        await wait_msg.edit_text(
            f"✅ **نتیجه ترجمه:**\n\n`{escape_markdown(result)}`", parse_mode="Markdown"
        )
        if not result.startswith("❌"):
            await log_upload_success("translation", chat_id)

    except Exception as e:
        print(f"Translation Handler Error: {e}")
        await safe_edit_or_reply(wait_msg or update.message, "❌ خطای سیستمی رخ داد.")

    finally:
        # بسیار مهم: خروج کاربر از وضعیت ترجمه تا در پیام‌های بعدی گیر نکند
        clear_state(chat_id)
