# handlers/menus/web_scraper.py


from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import clear_state, get_state, set_state
from core.keyboards import get_google_search_menu_keyboard
from services.web_scraper import search_web


async def btn_web_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_google_search_menu")
    await update.message.reply_text(
        "🔍 جستجوی وب\n\nلطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_google_search_menu_keyboard(),
    )


async def btn_google_search_subject_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_google_search_subject")
    await update.message.reply_text(
        "🔍 لطفاً موضوعی که می‌خواهید جستجو کنید را بفرستید:"
    )


async def btn_google_search_link_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_google_search_link")
    await update.message.reply_text(
        "🔗 لطفاً لینکی از صفحه وب را بفرستید:\n\n(لینک باید با http:// یا https:// شروع شود)"
    )
