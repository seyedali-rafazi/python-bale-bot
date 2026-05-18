import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import set_state, get_state, clear_state
from core.keyboards import (
    get_yt_quality_telegram_keyboard,
    get_yt_quality_server_keyboard,
    get_main_menu_keyboard,
)
from core.database import is_vip, increment_yt_downloads
from services.youtube import get_video_filesize
from .task import background_yt_download


async def youtube_destination_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    # جلوگیری از ارور تایم‌اوت شبکه
    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    data = query.data
    chat_id = str(query.message.chat_id)

    if data not in ["ytdest_telegram", "ytdest_server"]:
        return

    user_state = await asyncio.to_thread(get_state, chat_id)
    if not user_state or user_state.get("step") != "waiting_yt_destination":
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    url = user_state.get("yt_url")
    format_type = user_state.get("format")

    if data == "ytdest_server":
        if not await is_vip(chat_id):
            await query.edit_message_text(
                "❌ این قابلیت فقط مخصوص کاربران ویژه (Pro ⭐️) می‌باشد."
            )
            return
        destination = "server"
    else:
        destination = "telegram"

    await asyncio.to_thread(
        set_state,
        chat_id,
        "waiting_yt_quality",
        yt_url=url,
        format=format_type,
        destination=destination,
    )

    if destination == "telegram":
        keyboard = get_yt_quality_telegram_keyboard()
        msg = "🎥 کیفیت ویدیو را انتخاب کنید (محدودیت: 1 گیگابایت):"
    else:
        keyboard = get_yt_quality_server_keyboard()
        msg = "🎥 کیفیت ویدیو را انتخاب کنید (محدودیت: 1 گیگابایت):"

    await query.edit_message_text(msg, reply_markup=keyboard)


async def youtube_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    data = query.data
    chat_id = str(query.message.chat_id)

    if not data.startswith("ytqual_"):
        return

    quality = data.split("_")[1]  # e.g., "144"

    user_state = await asyncio.to_thread(get_state, chat_id)
    if not user_state or user_state.get("step") not in [
        "waiting_yt_quality",
        "processing_yt_quality",
    ]:
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    if user_state.get("step") == "processing_yt_quality":
        await query.answer("⏳ در حال پردازش... لطفا صبر کنید.")
        return

    url = user_state.get("yt_url")
    format_type = user_state.get("format")
    destination = user_state.get("destination")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await asyncio.to_thread(
        set_state,
        chat_id,
        "processing_yt_quality",
        yt_url=url,
        format=format_type,
        destination=destination,
    )

    try:
        await query.edit_message_text(
            "⏳ در حال بررسی کیفیت، لطفا صبر کنید...", reply_markup=None
        )
    except Exception:
        pass

    try:
        if format_type == "video":
            estimated_size = await asyncio.to_thread(get_video_filesize, url, quality)
        else:
            estimated_size = await asyncio.to_thread(
                get_video_filesize, url, "bestaudio"
            )

        if destination == "telegram":
            limit = 1 * 1024 * 1024 * 1024  # 1GB
        else:
            limit = 1 * 1024 * 1024 * 1024  # 1GB

        if estimated_size and estimated_size > limit:
            size_mb = round(estimated_size / (1024 * 1024), 1)
            limit_mb = round(limit / (1024 * 1024), 1)

            if destination == "telegram":
                msg = (
                    f"❌ فایل حدود {size_mb} مگابایت است و بیشتر از 1 گیگابایت (1024 مگابایت) می‌باشد. "
                    "لطفاً کیفیت پایین‌تری انتخاب کنید."
                )
            else:
                msg = (
                    f"❌ فایل حدود {size_mb} مگابایت است و بیشتر از 1 گیگابایت (1024 مگابایت) می‌باشد. "
                    "لطفاً کیفیت پایین‌تری انتخاب کنید."
                )

            if destination == "telegram":
                keyboard = get_yt_quality_telegram_keyboard()
            else:
                keyboard = get_yt_quality_server_keyboard()

            await asyncio.to_thread(
                set_state,
                chat_id,
                "waiting_yt_quality",
                yt_url=url,
                format=format_type,
                destination=destination,
            )
            await query.edit_message_text(msg, reply_markup=keyboard)
            return
    except Exception as e:
        print(f"⚠️ Error checking filesize: {e}")
        if destination == "telegram":
            keyboard = get_yt_quality_telegram_keyboard()
        else:
            keyboard = get_yt_quality_server_keyboard()
        await asyncio.to_thread(
            set_state,
            chat_id,
            "waiting_yt_quality",
            yt_url=url,
            format=format_type,
            destination=destination,
        )
        await query.edit_message_text(
            "⚠️ خطا در محاسبه حجم فایل. لطفا دوباره یک کیفیت انتخاب کنید.",
            reply_markup=keyboard,
        )
        return

    await query.edit_message_text("✅ درخواست ثبت شد. در حال انتقال به صف دانلود...")

    await asyncio.to_thread(clear_state, chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔙 بازگشت به منوی اصلی",
        reply_markup=get_main_menu_keyboard(),
    )

    await increment_yt_downloads(chat_id)

    asyncio.create_task(
        background_yt_download(
            context, url, chat_id, format_type, destination, quality=quality
        )
    )
