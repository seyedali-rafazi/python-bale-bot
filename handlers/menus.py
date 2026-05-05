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
    get_tiktok_menu_keyboard,
)
from core.database import (
    get_user_info,
    get_yt_downloads,
    get_music_downloads,
    get_pinterest_downloads,
    is_vip,
    get_tt_explores,
    increment_tt_explores,
    get_random_tiktok_explore_videos,
    get_setting,
    get_tt_downloads,
    delete_invalid_video_from_db,
)
from datetime import datetime


async def btn_back_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .commands import cmd_start

    await cmd_start(update, context)


# یوتیوب


async def btn_yt_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # بررسی فعال بودن یوتیوب
    if get_setting("youtube_enabled", "1") == "0":
        await update.message.reply_text(
            "❌ بخش یوتیوب فعلاً توسط ادمین غیرفعال شده است."
        )
        return

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


async def btn_profile_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_info = get_user_info(user_id)

    if not user_info:
        await update.message.reply_text(
            "❌ اطلاعات شما یافت نشد. لطفاً دستور /start را ارسال کنید."
        )
        return

    username, is_vip, join_date, vip_expire_date = user_info

    username_str = f"@{username}" if username else "ندارد"

    vip_status_text = "🆓 رایگان"
    vip_duration_text = ""

    if is_vip == 1:
        vip_status_text = "💎 ویژه (پرو)"
        if vip_expire_date:
            try:
                expire_dt = datetime.fromisoformat(vip_expire_date)
                now = datetime.now()

                if expire_dt > now:
                    remaining_time = expire_dt - now
                    remaining_days = remaining_time.days + 1
                    vip_duration_text = f"\n⏳ اعتبار اشتراک: {remaining_days} روز"
                else:
                    vip_duration_text = "\n⏳ اعتبار اشتراک: منقضی شده"

            except Exception as e:
                print(f"Error parsing date for user {user_id}: {e}")
                vip_duration_text = "\n⏳ اعتبار اشتراک: نامشخص (خطا)"

    # دریافت آمار مصرف
    yt_count = get_yt_downloads(user_id)
    music_count = get_music_downloads(user_id)
    pinterest_count = get_pinterest_downloads(user_id)  # دریافت مصرف پینترست
    tt_dl_count = get_tt_downloads(user_id)
    tt_exp_count = get_tt_explores(user_id)

    # بررسی محدودیت‌ها
    yt_limit = "20" if is_vip == 1 else "1"
    music_limit = "20" if is_vip == 1 else "6"
    pinterest_limit = "30" if is_vip == 1 else "2"
    tt_dl_limit = "15" if is_vip == 1 else "1"
    tt_exp_limit = "10" if is_vip == 1 else "1"

    # ساختار متن نهایی
    profile_text = f"""
🪪 **مشخصات شما**
🆔 ایدی عددی: `{user_id}`
👤 یوزرنیم: {username_str}
📊 وضعیت اشتراک: {vip_status_text}{vip_duration_text}
📆 اولین استفاده: {join_date}

⏳ **مصرف امروز (به وقت ایران؛ ریست نیمه‌شب):**
• یوتیوب | دانلود: $ {yt_count} / {yt_limit} $
• موسیقی | دانلود: $ {music_count} / {music_limit} $
• پینترست | جستجو: $ {pinterest_count} / {pinterest_limit} $
• تیک‌تاک | دانلود: $ {tt_dl_count} / {tt_dl_limit} $
• تیک‌تاک | اکسپلور: $ {tt_exp_count} / {tt_exp_limit} $
"""

    await update.message.reply_text(profile_text.strip(), parse_mode="Markdown")


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


# برنامه نویسی end

#  موسیقی start


async def btn_music_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 به بخش موسیقی خوش آمدید!\nیک گزینه را انتخاب کنید 👇",
        reply_markup=get_music_menu_keyboard(),
    )


async def btn_music_track_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_track")
    await update.message.reply_text("🔍 نام آهنگ یا خواننده را بفرستید:")


async def btn_music_album_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_album")
    await update.message.reply_text("💿 نام آلبوم را برای جستجو بفرستید:")


async def btn_music_artist_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_artist")
    await update.message.reply_text("🎤 نام خواننده مورد نظر را بفرستید:")


async def btn_music_playlist_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_playlist")
    await update.message.reply_text("🎧 نام یا موضوع پلی‌لیست را بفرستید:")


#  موسیقی end

#  پینترست start


async def btn_pinterest_req(update, context):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_pinterest")
    await update.message.reply_text(
        "📌 کلمه یا موضوعی که می‌خواهید عکس آن را ببینید بفرستید:"
    )


#  پینترست end

#  تیک تاک start


async def btn_tiktok_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 به بخش تیک‌تاک خوش آمدید. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_tiktok_menu_keyboard(),
    )


async def btn_tt_link_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tt_link")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیوی تیک‌تاک (یا یوزر لینک) را بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tt_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_tt_search")
    await update.message.reply_text(
        "🔍 لطفاً کلمه کلیدی یا موضوع مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_tt_trend_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # مستقیم به تابع پردازش ترند ارجاع می‌دهیم
    from handlers.states.state_tiktok import process_tiktok_trends

    await process_tiktok_trends(update, context)


async def btn_tt_explore_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # دریافت تعداد بیشتری ویدیو (مثلا ۲۰ تا) به جای ۵ تا
    videos = get_random_tiktok_explore_videos(20)
    if not videos:
        await update.message.reply_text("❌ هنوز ویدیویی در اکسپلور ذخیره نشده است.")
        return

    await update.message.reply_text("🌍 در حال ارسال ویدیوهای اکسپلور...")

    sent_count = 0

    for vid in videos:
        # اگر ۵ ویدیو سالم ارسال شد، حلقه را متوقف کن
        if sent_count >= 5:
            break

        try:
            # تلاش برای ارسال ویدیو
            await context.bot.send_video(chat_id=chat_id, video=vid)
            sent_count += 1

        except Exception as e:
            # اگر ارسال خطا داد، یعنی file_id منقضی شده است
            print(f"Error sending video {vid}: {e}")

            # ⚠️ مهم: تابعی بنویسید که این file_id را از دیتابیس شما پاک کند
            delete_invalid_video_from_db(vid)

    # اگر حداقل یک ویدیو با موفقیت ارسال شد، سهمیه کاربر را ثبت کن
    if sent_count > 0:
        increment_tt_explores(user_id)
    else:
        await update.message.reply_text(
            "❌ متاسفانه ویدیوهای موجود منقضی شده‌اند. در حال پاکسازی دیتابیس..."
        )


#  تیک تاک end

#  گیتهاب start


async def btn_prog_github_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.keyboards import get_github_menu_keyboard

    await update.message.reply_text(
        "به بخش گیت‌هاب خوش آمدید:", reply_markup=get_github_menu_keyboard()
    )


async def btn_gh_dl_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(str(update.effective_chat.id), "waiting_gh_dl")
    await update.message.reply_text(
        "🔗 لینک یا نام کامل ریپازیتوری را وارد کنید (مثال: microsoft/vscode):"
    )


async def btn_gh_user_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(str(update.effective_chat.id), "waiting_gh_user")
    await update.message.reply_text("👤 نام کاربری گیت‌هاب را ارسال کنید:")


#  گیتهاب end
