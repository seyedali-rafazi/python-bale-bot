# handlers/commands.py

import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import clear_state, set_state
from core.keyboards import get_main_menu_keyboard
from core.constants import BTN_BACK
from services.book import search_books
from services.translator import translate_text
from services.weather import get_weather_forecast

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    clear_state(chat_id)
    await update.message.reply_text(
        "👋 به ربات خوش آمدید!\n\nلطفاً یک گزینه را انتخاب کنید 👇",
        reply_markup=get_main_menu_keyboard()
    )

async def cmd_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ نام کتاب وارد نشده است. مثال:\n`/book python`")
        return
        
    query = " ".join(context.args)
    chat_id = str(update.effective_chat.id)
    
    await update.message.reply_text(f"⏳ در حال جستجو برای `{query}`...")
    results = await asyncio.to_thread(search_books, query)
    
    if not results:
        await update.message.reply_text("❌ متأسفانه کتابی پیدا نشد.")
        return
        
    res_text = f"🔎 **نتایج برای:** {query}\n\n"
    download_buttons = []
    
    for i, book in enumerate(results, 1):
        res_text += f"{i}️⃣ **{book['title']}**\n👤 نویسنده: {book['author']}\n🌐 منبع: {book['source']}\n〰️〰️〰️\n"
        if book['has_pdf']:
            download_buttons.append(KeyboardButton(f"📥 دانلود شماره {i}"))
        
    keyboard = [download_buttons[i:i+2] for i in range(0, len(download_buttons), 2)]
    keyboard.append([KeyboardButton(BTN_BACK)])
    
    set_state(chat_id, 'waiting_book_selection', books=results)
    await update.message.reply_text(res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ فرمت اشتباه است. مثال: `/tr fa:en سلام`")
        return
        
    lang_config = context.args[0]
    text_to_translate = " ".join(context.args[1:])
    
    if ':' not in lang_config:
        await update.message.reply_text("❌ فرمت زبان‌ها اشتباه است.")
        return
        
    source_lang, target_lang = lang_config.split(':', 1)
    await update.message.reply_text(f"⏳ در حال ترجمه...")
    result = await asyncio.to_thread(translate_text, source_lang, target_lang, text_to_translate)
    await update.message.reply_text(f"✅ **ترجمه:**\n\n{result}")

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ نام شهر وارد نشده است. مثال: `/weather Tehran`")
        return
        
    city_name = " ".join(context.args)
    await update.message.reply_text(f"⏳ در حال دریافت آب و هوای {city_name}...")
    result = await asyncio.to_thread(get_weather_forecast, city_name)
    await update.message.reply_text(result)
