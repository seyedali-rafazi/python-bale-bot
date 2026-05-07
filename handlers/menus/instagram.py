from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_insta_menu_keyboard


async def btn_ig_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 به بخش اینستاگرام خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_insta_menu_keyboard(),
    )


async def btn_ig_link_dl_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک پست یا ریلز اینستاگرام را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ig_last_post_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_last_post")
    await update.message.reply_text(
        "🖼 لطفاً آیدی پیج یا لینک پروفایل اینستاگرام را بفرستید (پیج باید Public باشد):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )
