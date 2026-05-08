from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_translation_menu_keyboard
from handlers.ensure_membership import ensure_membership


async def btn_tr_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "🔤 به بخش ترجمه خوش آمدید. لطفاً جهت ترجمه را انتخاب کنید 👇",
        reply_markup=get_translation_menu_keyboard(),
    )


async def btn_tr_fa_en_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tr_fa_en")
    await update.message.reply_text(
        "🇮🇷 لطفاً متن فارسی خود را برای ترجمه به انگلیسی بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tr_en_fa_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tr_en_fa")
    await update.message.reply_text(
        "🇬🇧 لطفاً متن انگلیسی خود را برای ترجمه به فارسی بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )
