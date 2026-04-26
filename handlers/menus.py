# handlers/menus.py

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
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
    get_programming_menu_keyboard,
)


async def btn_back_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .commands import cmd_start

    await cmd_start(update, context)


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

# هواشناسی start


async def btn_weather_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_weather_city")
    await update.message.reply_text(
        "🌍 لطفاً نام شهر مورد نظر خود را به صورت **انگلیسی** وارد کنید (مثال: Shiraz):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# هواشناسی end

# دانلود کتاب start


async def btn_book_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_book_search")
    await update.message.reply_text(
        "📚 لطفاً نام کتاب مورد نظر خود را به صورت انگلیسی وارد کنید (مثال: python):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# دانلود کتاب end


# پشتیبانی start


async def btn_support_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💬 ارتباط با پشتیبانی در بله", url=BALE_SUPPORT_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "برای ارتباط با پشتیبانی، طرح پیشنهادات و گزارش مشکلات، روی دکمه زیر کلیک کنید:",
        reply_markup=reply_markup,
    )


# پشتیبانی end

# برنامه نویسی start


async def btn_programming_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👨‍💻 به بخش برنامه‌نویسی خوش آمدید. چه افزونه‌ای نیاز دارید؟",
        reply_markup=get_programming_menu_keyboard(),
    )


async def btn_prog_chrome_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_prog_chrome")
    await update.message.reply_text(
        "🌐 لینک، نام افزونه یا ID (32 کاراکتری) افزونه کروم را ارسال کنید:"
    )


async def btn_prog_firefox_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_prog_firefox")
    await update.message.reply_text(
        "🦊 نام افزونه فایرفاکس را جهت جستجو و دانلود ارسال کنید:"
    )


async def btn_prog_vscode_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_prog_vscode")
    await update.message.reply_text(
        "💻 شناسه دقیق افزونه VS Code (مثال: esbenp.prettier-vscode) را ارسال کنید:"
    )


async def btn_prog_docs_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 به دلیل ساختار داینامیک داکیومنت‌ها، دانلود مستقیم PDF امکان‌پذیر نیست.\n\n"
        "💡 پیشنهاد: از نرم‌افزار **Zeal** (برای ویندوز/لینوکس) یا **Dash** (برای مک) جهت دانلود آفلاین داکیومنت زبان‌های برنامه‌نویسی استفاده کنید."
    )


# برنامه نویسی end
