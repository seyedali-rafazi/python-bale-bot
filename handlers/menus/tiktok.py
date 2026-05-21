# handlers/menus/tiktok.py

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_tiktok_menu_keyboard
from handlers.ensure_membership import ensure_membership


async def btn_tiktok_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "🎵 به بخش تیک‌تاک خوش آمدید. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_tiktok_menu_keyboard(),
    )


async def btn_tt_link_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tt_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیوی تیک‌تاک (یا یوزر لینک) را بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tt_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tt_search")
    await update.message.reply_text(
        "🔍 لطفاً کلمه کلیدی یا موضوع مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tt_trend_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    from handlers.states.state_tiktok import process_tiktok_trends

    await process_tiktok_trends(update, context)
