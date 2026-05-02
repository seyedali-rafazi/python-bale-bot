from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.database import get_pinterest_usage, increment_pinterest_usage, is_vip
from services.pinterest import search_pinterest_images


async def handle_pinterest_state(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: str
):
    user_id = str(update.effective_user.id)

    usage = get_pinterest_usage(user_id)
    user_is_vip = is_vip(user_id)
    limit = 30 if user_is_vip else 5

    if usage >= limit:
        await update.message.reply_text(
            "❌ محدودیت روزانه شما به پایان رسیده است! لطفا اشتراک VIP تهیه کنید."
        )
        set_state(chat_id, "")
        return

    msg = await update.message.reply_text("⏳ در حال جستجوی تصاویر...")
    images = search_pinterest_images(text, max_results=10)

    if not images:
        await msg.edit_text("❌ تصویری یافت نشد. کلمه دیگری امتحان کنید.")
        set_state(chat_id, "")
        return

    increment_pinterest_usage(user_id)

    # ذخیره تصاویر در context برای دکمه 'عکس‌های بیشتر'
    context.user_data["pin_images"] = images
    context.user_data["pin_index"] = 5

    media_group = [InputMediaPhoto(media=img) for img in images[:5]]

    await msg.delete()
    await context.bot.send_media_group(chat_id=chat_id, media=media_group)

    keyboard = [[InlineKeyboardButton("➕ عکس‌های بیشتر", callback_data="more_pins")]]
    await context.bot.send_message(
        chat_id=chat_id,
        text="برای دریافت عکس‌های بیشتر کلیک کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    set_state(chat_id, "")


async def handle_more_pins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    images = context.user_data.get("pin_images", [])
    index = context.user_data.get("pin_index", 0)

    if index >= len(images):
        await query.edit_message_text("❌ عکس بیشتری برای این کلمه وجود ندارد.")
        return

    media_group = [InputMediaPhoto(media=img) for img in images[index : index + 5]]
    context.user_data["pin_index"] = index + 5

    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media_group)
