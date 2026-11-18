# handlers/commands.py

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import clear_state
from core.keyboards import get_main_menu_keyboard
from services.translator import translate_text
from services.weather import get_weather_forecast
from core.database import add_user, log_user_active, log_upload_success
from handlers.ensure_membership import CHANNEL_URL, is_user_channel_member


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

    # ثبت کاربر در دیتابیس
    await add_user(chat_id, username)
    await log_user_active(chat_id)

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
    await msg.reply_text(
        "👋 به ربات خوش آمدید!\n\nلطفاً یک گزینه را انتخاب کنید 👇",
        reply_markup=get_main_menu_keyboard(),
    )


async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ فرمت اشتباه است. مثال: `/tr fa:en سلام`")
        return

    lang_config = context.args[0]
    text_to_translate = " ".join(context.args[1:])

    if ":" not in lang_config:
        await update.message.reply_text("❌ فرمت زبان‌ها اشتباه است.")
        return

    source_lang, target_lang = lang_config.split(":", 1)
    await update.message.reply_text(f"⏳ در حال ترجمه...")
    result = await asyncio.to_thread(
        translate_text, source_lang, target_lang, text_to_translate
    )
    await update.message.reply_text(f"✅ **ترجمه:**\n\n{result}")
    await log_upload_success("translation", str(update.effective_chat.id))


async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ نام شهر وارد نشده است. مثال: `/weather Tehran`"
        )
        return

    city_name = " ".join(context.args)
    await update.message.reply_text(f"⏳ در حال دریافت آب و هوای {city_name}...")
    result = await get_weather_forecast(city_name)
    await update.message.reply_text(result, parse_mode="Markdown")
    await log_upload_success("weather", str(update.effective_chat.id))
