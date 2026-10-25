# handlers/menus/software.py

from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.keyboards import get_software_menu_keyboard
from handlers.ensure_membership import ensure_membership


async def btn_software_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show software download platform submenu (Android / Windows)."""
    if not await ensure_membership(update, context):
        return

    await update.message.reply_text(
        "📦 **بخش دانلود نرم‌افزار**\n\n"
        "لطفاً پلتفرم مورد نظر خود را انتخاب کنید:\n"
        "• 📱 **اندروید:** جستجو و دریافت مستقیم فایل‌های APK معتبر\n"
        "• 💻 **ویندوز:** جستجو و دریافت فایل‌های نصبی (EXE / MSI / ZIP)",
        reply_markup=get_software_menu_keyboard(),
        parse_mode="Markdown",
    )


async def btn_software_android_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set state to waiting_software_android and prompt user."""
    if not await ensure_membership(update, context):
        return

    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_software_android")
    await update.message.reply_text(
        "📱 **دانلود نرم‌افزار اندروید**\n\n"
        "نام برنامه مورد نظر خود را به انگلیسی یا فارسی بنویسید:\n"
        "_(مثال: `v2rayng` یا `telegram` یا `اینستاگرام`)_\n\n"
        "🔙 برای بازگشت، از دکمه «بازگشت به منو» استفاده کنید.",
        parse_mode="Markdown",
    )


async def btn_software_windows_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set state to waiting_software_windows and prompt user."""
    if not await ensure_membership(update, context):
        return

    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_software_windows")
    await update.message.reply_text(
        "💻 **دانلود نرم‌افزار ویندوز**\n\n"
        "نام نرم‌افزار مورد نظر خود را به انگلیسی یا فارسی بنویسید:\n"
        "_(مثال: `vlc` یا `telegram` یا `chrome` یا `7zip`)_\n\n"
        "🔙 برای بازگشت، از دکمه «بازگشت به منو» استفاده کنید.",
        parse_mode="Markdown",
    )
