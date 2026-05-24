# handlers/states/state_translation.py

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.translator import translate_text
from core.state_manager import clear_state  # فرض بر اینکه این تابع را دارید
from core.database import log_upload_success

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
            # فراخوانی سرویس ترجمه در ترد جداگانه تا ربات هنگ نکند
            result = await asyncio.to_thread(translate_text, source, target, text)

        # ویرایش پیام انتظار به جای ارسال یک پیام جدید (UX بهتر)
        await wait_msg.edit_text(
            f"✅ **نتیجه ترجمه:**\n\n`{result}`", parse_mode="Markdown"
        )
        await log_upload_success("translation", chat_id)

    except Exception as e:
        print(f"Translation Handler Error: {e}")
        await update.message.reply_text("❌ خطای سیستمی رخ داد.")

    finally:
        # بسیار مهم: خروج کاربر از وضعیت ترجمه تا در پیام‌های بعدی گیر نکند
        clear_state(chat_id)
