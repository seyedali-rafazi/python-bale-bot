from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_ai_menu_keyboard


async def btn_ai_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 به بخش هوش مصنوعی خوش آمدید!\nلطفاً یک گزینه را انتخاب کنید 👇",
        reply_markup=get_ai_menu_keyboard(),
    )


async def btn_ai_chat_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_chat")
    await update.message.reply_text(
        "💬 دستیار هوشمند آماده است!\nسوال یا متن خود را بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_ocr_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_ocr")
    await update.message.reply_text(
        "🖼 لطفاً عکسی که دارای متن است را ارسال کنید (به صورت Photo):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_tts_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_tts")
    await update.message.reply_text(
        "🗣 لطفاً متنی که می‌خواهید به صدا تبدیل شود را بفرستید (پشتیبانی از فارسی و انگلیسی):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_image_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_image")
    await update.message.reply_text(
        "🎨 لطفاً توصیف عکسی که می‌خواهید ساخته شود را بنویسید (برای نتیجه بهتر انگلیسی بنویسید):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )
