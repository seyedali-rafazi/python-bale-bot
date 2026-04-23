# handlers/menus.py

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import *
from core.keyboards import (
    get_ai_menu_keyboard,
    get_music_menu_keyboard,
    get_telegram_menu_keyboard,
    get_youtube_menu_keyboard,
    get_insta_menu_keyboard,
    get_translation_menu_keyboard,
)


async def btn_back_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .commands import cmd_start

    await cmd_start(update, context)


async def btn_book_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "📚 برای جستجوی کتاب دستور زیر را بفرستید:\n`/book [نام کتاب]`\nمثال: `/book python`"
    await update.message.reply_text(
        help_text,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_weather_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "🌤 برای مشاهده آب و هوا از دستور `/weather` استفاده کنید.\nمثال:\n`/weather Shiraz`"
    await update.message.reply_text(
        help_text,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# یوتیوب


async def btn_yt_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📺 به بخش پیشرفته یوتیوب خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_youtube_menu_keyboard(),
    )


async def btn_yt_last5_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_last5_channel")
    await update.message.reply_text(
        "آیدی یا نام کاربری کانال یوتیوب را بفرستید (مثال: mrbeast@ یا mrbeast):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_ch_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_ch_search_name")
    await update.message.reply_text(
        "ابتدا آیدی کانال مورد نظر را بفرستید (مثال: mrbeast@):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_global_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_global_search")
    await update.message.reply_text(
        "موضوع یا نام ویدیوی مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_link_vid_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_link", format="video")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیو یوتیوب را برای دانلود (تصویری) ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_yt_link_mp3_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_link", format="audio")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیو یوتیوب را برای تبدیل به فایل صوتی (MP3) ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 به بخش هوش مصنوعی خوش آمدید!\nلطفاً یک گزینه را انتخاب کنید 👇",
        reply_markup=get_ai_menu_keyboard(),
    )


async def btn_ai_chat_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_chat")
    await update.message.reply_text(
        "💬 دستیار هوشمند آماده است!\nسوال یا متن خود را بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_ocr_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_ocr")
    await update.message.reply_text(
        "🖼 لطفاً عکسی که دارای متن است را ارسال کنید (به صورت Photo):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_tts_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_tts")
    await update.message.reply_text(
        "🗣 لطفاً متنی که می‌خواهید به صدا تبدیل شود را بفرستید (پشتیبانی از فارسی و انگلیسی):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ai_image_req(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ai_image")
    await update.message.reply_text(
        "🎨 لطفاً توصیف عکسی که می‌خواهید ساخته شود را بنویسید (برای نتیجه بهتر انگلیسی بنویسید):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_music_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 به بخش موسیقی خوش آمدید!\nیک گزینه را انتخاب کنید 👇",
        reply_markup=get_music_menu_keyboard(),
    )


async def btn_music_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_search")
    await update.message.reply_text(
        "🔍 لطفاً نام آهنگ یا خواننده مورد نظر خود را بنویسید (مثلاً: شجریان مرغ سحر):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_spotify_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_spotify_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک آهنگ اسپاتیفای را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_telegram_menu(update, context):
    await update.message.reply_text(
        "به منوی تلگرام خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_telegram_menu_keyboard(),
    )


async def btn_tg_single_req(update, context):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tg_single")
    await update.message.reply_text(
        "لطفاً لینک پیام تلگرام را بفرستید (مثال: https://t.me/channel_id/1234):"
    )


async def btn_tg_latest_req(update, context):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tg_latest")
    await update.message.reply_text(
        "لطفاً آیدی کانال عمومی تلگرام را بفرستید (مثال: @varzesh3 یا varzesh3):"
    )


# اینستاگرام start


async def btn_ig_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط منو را نشان می‌دهد
    await update.message.reply_text(
        "📸 به بخش اینستاگرام خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_insta_menu_keyboard(),
    )


async def btn_ig_link_dl_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک پست یا ریلز اینستاگرام را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_ig_last_post_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_ig_last_post")
    await update.message.reply_text(
        "🖼 لطفاً آیدی پیج یا لینک پروفایل اینستاگرام را بفرستید (پیج باید Public باشد):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# اینستاگرام end

# ترجمه start


async def btn_tr_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔤 به بخش ترجمه خوش آمدید. لطفاً جهت ترجمه را انتخاب کنید 👇",
        reply_markup=get_translation_menu_keyboard(),
    )


async def btn_tr_fa_en_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tr_fa_en")
    await update.message.reply_text(
        "🇮🇷 لطفاً متن فارسی خود را برای ترجمه به انگلیسی بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tr_en_fa_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tr_en_fa")
    await update.message.reply_text(
        "🇬🇧 لطفاً متن انگلیسی خود را برای ترجمه به فارسی بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# ترجمه end
