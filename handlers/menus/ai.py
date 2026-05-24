# handlers/menus/ai.py

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_ai_menu_keyboard
from handlers.ensure_membership import ensure_membership


async def btn_ai_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "🤖 به بخش هوش مصنوعی خوش آمدید!\n\n"
        "💬 **دستیار هوشمند** فقط پیام **متنی** می‌پذیرد "
        "(عکس، صدا، ویدیو و فایل پشتیبانی نمی‌شود).\n"
        "سایر گزینه‌های این منو (OCR، صدا، تصویر و …) جداگانه کار می‌کنند.\n\n"
        "لطفاً یک گزینه را انتخاب کنید 👇",
        reply_markup=get_ai_menu_keyboard(),
        parse_mode="Markdown",
    )


async def btn_ai_chat_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return

    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_chat")
    await update.message.reply_text(
        "💬 دستیار هوشمند آماده است!\n\n"
        "فقط **متن** بفرستید — عکس، صدا، ویدیو و فایل پذیرفته نمی‌شود.\n"
        "سوال یا متن خود را بنویسید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
        parse_mode="Markdown",
    )


async def btn_ai_ocr_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_ocr")
    await update.message.reply_text(
        "🖼 لطفاً عکسی که دارای متن است را ارسال کنید (به صورت Photo):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_tts_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_tts")
    await update.message.reply_text(
        "🗣 لطفاً متنی که می‌خواهید به صدا تبدیل شود را بفرستید (پشتیبانی از فارسی و انگلیسی):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_image_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_image")
    await update.message.reply_text(
        "🎨 لطفاً توصیف عکسی که می‌خواهید ساخته شود را بنویسید (برای نتیجه بهتر انگلیسی بنویسید):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )
