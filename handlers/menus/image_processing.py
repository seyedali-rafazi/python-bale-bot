# handlers/menus/image_processing.py

from telegram import Update
from telegram.ext import ContextTypes
from core.keyboards import get_image_processing_menu_keyboard
from core.state_manager import set_state


async def btn_image_processing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show image processing menu"""
    await update.message.reply_text(
        "🖼 **منوی پردازش تصویر**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=get_image_processing_menu_keyboard(),
    )


async def btn_img_create_pdf_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request images for PDF creation"""
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "img_create_pdf")

    await update.message.reply_text(
        "📄 **ساخت PDF از عکس‌ها**\n\n"
        "لطفاً عکس‌های خود را یکی یکی ارسال کنید.\n"
        "پس از ارسال همه عکس‌ها، عبارت 'تمام' یا 'done' را ارسال کنید.\n\n"
        "⚠️ حداکثر 20 عکس می‌توانید ارسال کنید."
    )


async def btn_img_convert_format_req(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Request image for format conversion"""
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "img_convert_format")

    await update.message.reply_text(
        "🔄 **تبدیل فرمت عکس**\n\n"
        "لطفاً عکس خود را ارسال کنید.\n"
        "سپس فرمت مورد نظر را انتخاب کنید:\n\n"
        "• PNG\n"
        "• JPG/JPEG\n"
        "• WEBP\n"
        "• BMP\n"
        "• GIF"
    )


async def btn_img_resize_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request image for resizing"""
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "img_resize")

    await update.message.reply_text(
        "📏 **تغییر اندازه عکس**\n\n"
        "لطفاً عکس خود را ارسال کنید.\n"
        "سپس ابعاد جدید را به فرمت زیر وارد کنید:\n\n"
        "مثال: `800x600` یا `50%` برای کاهش 50 درصدی"
    )


async def btn_img_remove_bg_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request image for background removal"""
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "img_remove_bg")

    await update.message.reply_text(
        "✂️ **حذف پس‌زمینه عکس**\n\n"
        "لطفاً عکس خود را ارسال کنید.\n"
        "پس‌زمینه عکس به صورت خودکار حذف خواهد شد.\n\n"
        "⚠️ این ویژگی برای عکس‌های با سوژه مشخص (مثل افراد، اشیاء) بهتر کار می‌کند."
    )


async def btn_img_video_to_gif_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request video for converting to GIF"""
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "img_video_to_gif")

    await update.message.reply_text(
        "🎬 **تبدیل ویدیو به GIF**\n\n"
        "لطفاً ویدیوی خود را ارسال کنید تا آن را به فایل متحرک GIF تبدیل کنم.\n\n"
        "⚠️ توجه داشته باشید حجم ویدیو زیاد نباشد تا فرآیند تبدیل سریع‌تر انجام شود."
    )


async def btn_img_extract_audio_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request video for audio extraction"""
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "img_extract_audio")

    await update.message.reply_text(
        "🎵 **استخراج صدا از ویدیو**\n\n"
        "لطفاً ویدیوی خود را ارسال کنید تا صدای آن را استخراج کنم و به صورت فایل صوتی MP3 برای شما بفرستم."
    )


# Made with Bob
