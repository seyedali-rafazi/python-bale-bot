from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state
from handlers.ensure_membership import ensure_membership


async def btn_prog_github_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    from core.keyboards import get_github_menu_keyboard

    await update.message.reply_text(
        "به بخش گیت‌هاب خوش آمدید:", reply_markup=get_github_menu_keyboard()
    )


async def btn_gh_dl_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    set_state(str(update.effective_chat.id), "waiting_gh_dl")
    await update.message.reply_text(
        "🔗 لینک یا نام کامل ریپازیتوری را وارد کنید (مثال: microsoft/vscode):"
    )


async def btn_gh_user_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    set_state(str(update.effective_chat.id), "waiting_gh_user")
    await update.message.reply_text("👤 نام کاربری گیت‌هاب را ارسال کنید:")


async def btn_gh_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    from core.state_manager import set_state

    set_state(str(update.effective_chat.id), "waiting_gh_search")
    await update.message.reply_text(
        "🔍 کلمه یا نام پروژه‌ای که می‌خواهید در گیت‌هاب جستجو کنید را وارد کنید:"
    )
