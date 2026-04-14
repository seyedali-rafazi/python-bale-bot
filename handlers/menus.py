# handlers/menus.py

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import *
from core.keyboards import get_main_menu_keyboard
from core.keyboards import get_ai_menu_keyboard
from core.keyboards import get_music_menu_keyboard

async def btn_back_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .commands import cmd_start
    await cmd_start(update, context)

async def btn_book_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "📚 برای جستجوی کتاب دستور زیر را بفرستید:\n`/book [نام کتاب]`\nمثال: `/book python`"
    await update.message.reply_text(help_text, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))

async def btn_tr_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "🔤 برای ترجمه از دستور `/tr` استفاده کنید.\nمثال:\n`/tr fa:en سلام`"
    await update.message.reply_text(help_text, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))

async def btn_weather_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "🌤 برای مشاهده آب و هوا از دستور `/weather` استفاده کنید.\nمثال:\n`/weather Shiraz`"
    await update.message.reply_text(help_text, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))

async def btn_yt_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_yt_link')
    await update.message.reply_text("🔗 لطفاً لینک ویدیو یوتیوب را ارسال کنید:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))

async def btn_ig_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_ig_link')
    await update.message.reply_text("📸 لطفاً لینک اینستاگرام را ارسال کنید:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))

async def btn_ai_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 به بخش هوش مصنوعی خوش آمدید!\nلطفاً یک گزینه را انتخاب کنید 👇", 
        reply_markup=get_ai_menu_keyboard()
    )

async def btn_ai_chat_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_ai_chat')
    await update.message.reply_text(
        "💬 دستیار هوشمند آماده است!\nسوال یا متن خود را بفرستید:", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
    )

async def btn_ai_ocr_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_ai_ocr')
    await update.message.reply_text(
        "🖼 لطفاً عکسی که دارای متن است را ارسال کنید (به صورت Photo):", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
    )

async def btn_ai_tts_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_ai_tts')
    await update.message.reply_text(
        "🗣 لطفاً متنی که می‌خواهید به صدا تبدیل شود را بفرستید (پشتیبانی از فارسی و انگلیسی):", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
    )

async def btn_ai_image_req(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_ai_image')
    await update.message.reply_text(
        "🎨 لطفاً توصیف عکسی که می‌خواهید ساخته شود را بنویسید (برای نتیجه بهتر انگلیسی بنویسید):", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
    )

async def btn_music_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 به بخش موسیقی خوش آمدید!\nیک گزینه را انتخاب کنید 👇", 
        reply_markup=get_music_menu_keyboard()
    )

async def btn_music_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_music_search')
    await update.message.reply_text(
        "🔍 لطفاً نام آهنگ یا خواننده مورد نظر خود را بنویسید (مثلاً: شجریان مرغ سحر):", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
    )

async def btn_spotify_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, 'waiting_spotify_link')
    await update.message.reply_text(
        "🔗 لطفاً لینک آهنگ اسپاتیفای را ارسال کنید:", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
    )