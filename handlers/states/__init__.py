# handlers/states/__init__.py

from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import get_state
from .state_programming import handle_programming_state
from .state_book import handle_book_state
from .state_youtube import handle_youtube_state
from .state_insta import handle_insta_state
from .state_ai import handle_ai_state, handle_ai_photo
from .state_music import handle_music_state
from .state_telegram import handle_telegram_state
from .state_translation import handle_translation_state
from .state_weather import handle_weather_state


async def process_state_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get("step")

    # بازگشت سریع به منو
    if text in ["0", "لغو", "شروع"]:
        from handlers.commands import cmd_start  # ایمپورت از یک سطح بالاتر

        await cmd_start(update, context)
        return

    if not step:
        await update.message.reply_text("لطفاً از منو استفاده کنید.")
        return

    # 🌟 مسیریابی بر اساس نام step
    if step.startswith("waiting_book"):
        await handle_book_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_yt"):
        await handle_youtube_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_ig"):
        await handle_insta_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_ai"):
        await handle_ai_state(update, context, step, text, chat_id, state_data)

    elif step in ["waiting_music_search", "waiting_spotify_link"]:
        await handle_music_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_tg"):
        await handle_telegram_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_tr"):
        await handle_translation_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_weather"):
        await handle_weather_state(update, context, step, text, chat_id, state_data)

    elif step.startswith("waiting_prog"):
        await handle_programming_state(update, context, step, text, chat_id, state_data)


async def process_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get("step") if state_data else None

    if step == "waiting_ai_ocr":
        await handle_ai_photo(update, context, chat_id)
    else:
        await update.message.reply_text("متوجه نشدم. لطفاً از منو استفاده کنید.")
