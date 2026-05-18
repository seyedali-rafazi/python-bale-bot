# handlers/menus/web_scraper.py


from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import clear_state, get_state, set_state
from services.web_scraper import search_web


async def btn_web_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_web_search")
    await update.message.reply_text("🔍 لطفاً موضوعی که می‌خواهید جستجو کنید را بفرستید:")
