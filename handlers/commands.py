# handlers/commands.py

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import clear_state
from core.keyboards import get_main_menu_keyboard
from services.translator import async_translate_text
from services.weather import get_weather_forecast
from core.database import (
    add_user,
    get_tehran_today,
    log_user_active,
    log_upload_success,
)
from handlers.ensure_membership import CHANNEL_URL, ensure_membership, is_user_channel_member
from handlers.utils import escape_markdown
from services.cache_service import cache_get, cache_set


async def check_membership(bot, user_id):
    return await is_user_channel_member(bot, user_id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass

    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return

    chat_id = str(chat.id)
    username = chat.username

    # ثبت کاربر و لاگ فعالیت حداکثر یک‌بار در روز برای هر کاربر
    today = get_tehran_today()
    seen_key = f"start_seen:{today}:{chat_id}"
    if not await cache_get(seen_key):
        await asyncio.gather(
            add_user(chat_id, username),
            log_user_active(chat_id),
        )
        await cache_set(seen_key, 1, ttl_sec=86400)

    # بررسی جوین اجباری
    is_member = await check_membership(context.bot, chat_id)
    if not is_member:
        keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_URL)]]
        await msg.reply_text(
            "🛑 برای استفاده از ربات، ابتدا باید در کانال ما عضو شوید.\nپس از عضویت مجدداً /start را ارسال کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    clear_state(chat_id)
    from handlers.states.state_image_processing import cleanup_user_image_caches

    cleanup_user_image_caches(chat_id)
    await msg.reply_text(
        "👋 به ربات خوش آمدید!\n\n"
        "🔗 می‌توانید لینک یوتیوب، اینستاگرام، تیک‌تاک، تلگرام، گیت‌هاب، کاگل و... را مستقیم بفرستید "
        "یا یک گزینه از منو انتخاب کنید 👇",
        reply_markup=get_main_menu_keyboard(),
    )


async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ فرمت اشتباه است. مثال: `/tr fa:en سلام`")
        return

    lang_config = context.args[0]
    text_to_translate = " ".join(context.args[1:])

    if ":" not in lang_config:
        await update.message.reply_text("❌ فرمت زبان‌ها اشتباه است.")
        return

    source_lang, target_lang = lang_config.split(":", 1)
    await update.message.reply_text("⏳ در حال ترجمه...")
    try:
        result = await async_translate_text(source_lang, target_lang, text_to_translate)
    except Exception:
        await update.message.reply_text("❌ خطا در ترجمه! لطفاً کمی بعد دوباره تلاش کنید.")
        return
    await update.message.reply_text(f"✅ **ترجمه:**\n\n{escape_markdown(result)}")
    if not result.startswith("❌"):
        await log_upload_success("translation", str(update.effective_chat.id))


async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "❌ نام شهر وارد نشده است. مثال: `/weather Tehran`"
        )
        return

    city_name = " ".join(context.args)
    await update.message.reply_text(f"⏳ در حال دریافت آب و هوای {city_name}...")
    try:
        result = await get_weather_forecast(city_name)
    except Exception:
        await update.message.reply_text("❌ خطایی در دریافت اطلاعات آب و هوا رخ داد.")
        return
    await update.message.reply_text(result, parse_mode="Markdown")
    if not result.startswith("❌"):
        await log_upload_success("weather", str(update.effective_chat.id))
