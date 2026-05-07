from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.keyboards import get_programming_menu_keyboard


async def btn_programming_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👨‍💻 به بخش برنامه‌نویسی خوش آمدید. چه افزونه‌ای نیاز دارید؟",
        reply_markup=get_programming_menu_keyboard(),
    )


async def btn_prog_chrome_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_prog_chrome")
    await update.message.reply_text(
        "🌐 لینک، نام افزونه یا ID (32 کاراکتری) افزونه کروم را ارسال کنید:"
    )


async def btn_prog_firefox_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_prog_firefox")
    await update.message.reply_text(
        "🦊 نام افزونه فایرفاکس را جهت جستجو و دانلود ارسال کنید:"
    )


async def btn_prog_vscode_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_prog_vscode")
    await update.message.reply_text(
        "💻 شناسه دقیق افزونه VS Code (مثال: esbenp.prettier-vscode) را ارسال کنید:"
    )
