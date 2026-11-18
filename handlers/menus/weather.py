from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.keyboards import get_back_only_keyboard
from handlers.ensure_membership import ensure_membership


async def btn_weather_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_weather_city")
    await update.message.reply_text(
        "🌍 لطفاً نام شهر مورد نظر خود را وارد کنید (مثال: تهران یا Shiraz):",
        reply_markup=get_back_only_keyboard(),
    )
