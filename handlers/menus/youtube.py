import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.error import RetryAfter

from core.state_manager import set_state
from core.constants import BTN_BACK
from core.keyboards import get_youtube_menu_keyboard
from core.database import get_setting, get_top_cached_videos, get_user_info
from handlers.ensure_membership import ensure_membership


async def btn_yt_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return

    # دریافت اطلاعات کاربر از دیتابیس
    user_id = update.effective_user.id
    user_info = await get_user_info(user_id)

    # بررسی VIP بودن (is_vip در ایندکس 1 خروجی دیتابیس است)
    is_vip = user_info[1] if user_info else 0

    if not is_vip:
        await update.message.reply_text(
            "❌ به دلیل مشکلات زیر ساختی بله در اپلود فایل این قسمت مخصوص مشترکان pro میباشد میتوایند از دیگر بخش های ربات استفاده بفرمایید .❌"
        )
        return

    if await get_setting("youtube_enabled", "1") == "0":
        await update.message.reply_text(
            "❌ بخش یوتیوب فعلاً توسط ادمین غیرفعال شده است."
        )
        return

    await update.message.reply_text(
        "📺 به بخش پیشرفته یوتیوب خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_youtube_menu_keyboard(),
    )


async def btn_yt_last5_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_last5_channel")
    await update.message.reply_text(
        "آیدی یا نام کاربری کانال یوتیوب را بفرستید (مثال: mrbeast@ یا mrbeast):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_ch_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_ch_search_name")
    await update.message.reply_text(
        "ابتدا آیدی کانال مورد نظر را بفرستید (مثال: mrbeast@):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_global_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_global_search")
    await update.message.reply_text(
        "موضوع یا نام ویدیوی مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_link_vid_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_link", format="video")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیو یوتیوب را برای دانلود (تصویری) ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_link_mp3_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_link", format="audio")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیو یوتیوب را برای تبدیل به فایل صوتی (MP3) ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_top_videos_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    top_videos = await get_top_cached_videos(4)

    if not top_videos:
        await update.message.reply_text("📭 هنوز ویدیویی در کش سیستم ثبت نشده است.")
        return

    await update.message.reply_text(
        "🔥 در حال ارسال 4 ویدیوی پربازدید سیستم...\nلطفاً کمی صبر کنید."
    )

    chat_id = update.effective_chat.id

    for index, video in enumerate(top_videos):
        try:
            file_ids = json.loads(video["file_ids"])
            views = video["view_count"]
            video_id = video["video_id"]

            if file_ids:
                total_parts = len(file_ids)

                for part_index, file_id in enumerate(file_ids):
                    if total_parts > 1:
                        caption = (
                            f"🏅 رتبه: {index + 1} (پارت {part_index + 1} از {total_parts})\n"
                            f"👁 بازدید: {views}\n"
                            f"🔗 آیدی ویدیو: {video_id}"
                        )
                    else:
                        caption = (
                            f"🏅 رتبه: {index + 1}\n"
                            f"👁 بازدید: {views}\n"
                            f"🔗 آیدی ویدیو: {video_id}"
                        )

                    try:
                        await context.bot.send_video(
                            chat_id=chat_id, video=file_id, caption=caption
                        )
                        await asyncio.sleep(1.5)

                    except RetryAfter as e:
                        print(f"Rate limited! Sleeping for {e.retry_after} seconds...")
                        await asyncio.sleep(e.retry_after)
                        await context.bot.send_video(
                            chat_id=chat_id, video=file_id, caption=caption
                        )
                        await asyncio.sleep(1.5)

        except Exception as e:
            print(f"Error sending top video {video.get('video_id', 'Unknown')}: {e}")
            continue
