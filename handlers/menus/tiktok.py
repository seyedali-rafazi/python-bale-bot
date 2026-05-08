from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_tiktok_menu_keyboard
from core.database import (
    is_vip,
    get_tt_explores,
    increment_tt_explores,
    get_random_tiktok_explore_videos,
    delete_invalid_video_from_db,
)
from handlers.ensure_membership import ensure_membership


async def btn_tiktok_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "🎵 به بخش تیک‌تاک خوش آمدید. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_tiktok_menu_keyboard(),
    )


async def btn_tt_link_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tt_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیوی تیک‌تاک (یا یوزر لینک) را بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tt_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tt_search")
    await update.message.reply_text(
        "🔍 لطفاً کلمه کلیدی یا موضوع مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tt_trend_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    from handlers.states.state_tiktok import process_tiktok_trends

    await process_tiktok_trends(update, context)


async def btn_tt_explore_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    vip = is_vip(user_id)
    max_exp = 10 if vip else 1
    current_exp = get_tt_explores(user_id)

    if current_exp >= max_exp:
        await update.message.reply_text(
            "❌ محدودیت روزانه اکسپلور تیک‌تاک شما به پایان رسیده است."
        )
        return

    videos = get_random_tiktok_explore_videos(20)
    if not videos:
        await update.message.reply_text("❌ هنوز ویدیویی در اکسپلور ذخیره نشده است.")
        return

    await update.message.reply_text("🌍 در حال ارسال ویدیوهای اکسپلور...")

    sent_count = 0

    for vid in videos:
        if sent_count >= 5:
            break

        try:
            await context.bot.send_video(chat_id=chat_id, video=vid)
            sent_count += 1

        except Exception as e:
            print(f"Error sending video {vid}: {e}")
            delete_invalid_video_from_db(vid)

    if sent_count > 0:
        increment_tt_explores(user_id)
    else:
        await update.message.reply_text(
            "❌ متاسفانه ویدیوهای موجود منقضی شده‌اند. در حال پاکسازی دیتابیس..."
        )
