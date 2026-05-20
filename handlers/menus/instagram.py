from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_insta_menu_keyboard
from core.database import (
    is_vip,
    get_ig_explores,
    increment_ig_explores,
    get_random_instagram_explore_media,
    delete_invalid_ig_from_db,
)
from handlers.ensure_membership import ensure_membership
from core.limits import get_limit


async def btn_ig_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "📸 به بخش اینستاگرام خوش آمدید. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_insta_menu_keyboard(),
    )


async def btn_ig_link_dl_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک پست یا ریلز اینستاگرام را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ig_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_search")
    await update.message.reply_text(
        "🔍 لطفاً کلمه کلیدی یا هشتگ مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ig_trend_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    from handlers.states.state_insta import process_instagram_trends

    await process_instagram_trends(update, context)


async def btn_ig_explore_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return

    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    vip = await is_vip(user_id)
    max_exp = get_limit("instagram_explore", vip)
    current_exp = await get_ig_explores(user_id)

    if current_exp >= max_exp:
        await update.message.reply_text(
            "❌ محدودیت روزانه اکسپلور اینستاگرام شما به پایان رسیده است."
        )
        return

    media_ids = await get_random_instagram_explore_media(20)
    if not media_ids:
        await update.message.reply_text(
            "❌ هنوز محتوایی در اکسپلور ذخیره نشده است."
        )
        return

    await update.message.reply_text("🌍 در حال ارسال پست‌های اکسپلور...")

    sent_count = 0
    for file_id in media_ids:
        if sent_count >= 5:
            break
        try:
            try:
                await context.bot.send_video(chat_id=chat_id, video=file_id)
            except Exception:
                try:
                    await context.bot.send_photo(chat_id=chat_id, photo=file_id)
                except Exception:
                    await context.bot.send_document(chat_id=chat_id, document=file_id)
            sent_count += 1
        except Exception as e:
            print(f"Error sending IG explore media {file_id}: {e}")
            await delete_invalid_ig_from_db(file_id)

    if sent_count > 0:
        await increment_ig_explores(user_id)
    else:
        await update.message.reply_text(
            "❌ متاسفانه محتوای موجود منقضی شده‌اند. در حال پاکسازی دیتابیس..."
        )


async def btn_ig_last_post_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_last_post")
    await update.message.reply_text(
        "🖼 لطفاً آیدی پیج یا لینک پروفایل اینستاگرام را بفرستید (پیج باید Public باشد):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )
