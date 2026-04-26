# handlers/__init__.py

import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    MessageHandler,
    CommandHandler,
    filters,
    ApplicationHandlerStop,
    CallbackQueryHandler,
)
from core.constants import *
from .commands import cmd_start, cmd_tr
from .menus import (
    btn_book_req,
    btn_weather_req,
    btn_yt_req,
    btn_ig_req,
    btn_ig_link_dl_req,
    btn_ig_last_post_req,
    btn_back_action,
    btn_ai_menu,
    btn_ai_chat_req,
    btn_ai_ocr_req,
    btn_ai_tts_req,
    btn_ai_image_req,
    btn_music_menu,
    btn_music_search_req,
    btn_spotify_req,
    btn_telegram_menu,
    btn_tg_single_req,
    btn_tg_latest_req,
    btn_yt_last5_req,
    btn_yt_ch_search_req,
    btn_yt_global_req,
    btn_yt_link_vid_req,
    btn_yt_link_mp3_req,
    btn_tr_help,
    btn_tr_fa_en_req,
    btn_tr_en_fa_req,
    btn_support_req,
    btn_programming_menu,
    btn_prog_chrome_req,
    btn_prog_firefox_req,
    btn_prog_vscode_req,
)
from .states import process_state_input, process_photo_input
from core.admin import cmd_stats, cmd_setvip, cmd_messageuser
import os
from dotenv import load_dotenv
from .states.state_programming import handle_chrome_callback


load_dotenv()
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_URL = os.getenv("CHANNEL_URL")


async def check_membership_middleware(update, context):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # اگر آیدی کانال تنظیم نشده بود، کاری نکن
    if not CHANNEL_ID:
        return

    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return  # کاربر عضو است، ادامه کار ربات
    except Exception:
        pass  # کاربر عضو نیست یا ربات در کانال ادمین نیست

    # اگر به اینجا رسیدیم یعنی کاربر عضو نیست
    keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_URL)]]
    await update.message.reply_text(
        "🛑 کاربر عزیز، برای استفاده از ربات حتماً باید در کانال ما عضو شوید.\n\n"
        "پس از عضویت در کانال، لطفاً دستور /start را برای ربات ارسال کنید.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    # متوقف کردن ادامه پردازش (تا ربات جواب دیگری ندهد)
    raise ApplicationHandlerStop()


def register_all_handlers(application):
    # این خط باعث می‌شود قبل از هر دستوری، جوین اجباری چک شود (گروه 1-)
    application.add_handler(
        MessageHandler(filters.ALL, check_membership_middleware), group=-1
    )

    # دستورات ادمین
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("setvip", cmd_setvip))
    application.add_handler(CommandHandler("messageuser", cmd_messageuser))

    # دستورات پایه
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("tr", cmd_tr))

    # دکمه‌های بازگشت
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_BACK)}$"), btn_back_action)
    )

    # دکمه‌های منوی اصلی

    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_DL_YOUTUBE)}$"), btn_yt_req)
    )

    # هندلرهای هوش مصنوعی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_AI)}$"), btn_ai_menu)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_CHAT)}$"), btn_ai_chat_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_OCR)}$"), btn_ai_ocr_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_TTS)}$"), btn_ai_tts_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_IMAGE)}$"), btn_ai_image_req)
    )

    # هندلرهای موسیقی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_MUSIC)}$"), btn_music_menu)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_MUSIC_SEARCH)}$"), btn_music_search_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_MUSIC_SPOTIFY)}$"), btn_spotify_req
        )
    )

    # هندلز های تلگرام
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TELEGRAM)}$"), btn_telegram_menu)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_TG_SINGLE)}$"), btn_tg_single_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_TG_LATEST)}$"), btn_tg_latest_req
        )
    )

    #  هندلرهای منوی یوتیوب
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_YT_LAST5)}$"), btn_yt_last5_req)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_YT_CH_SEARCH)}$"), btn_yt_ch_search_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_YT_GLOBAL)}$"), btn_yt_global_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_YT_LINK_VID)}$"), btn_yt_link_vid_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_YT_LINK_MP3)}$"), btn_yt_link_mp3_req
        )
    )

    #  هندلرهای منوی اینستاگرام
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_DL_INSTA)}$"), btn_ig_req)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_IG_LINK_DL)}$"), btn_ig_link_dl_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_IG_LAST_POST)}$"), btn_ig_last_post_req
        )
    )

    #  هندلرهای منوی ترجمه
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TRANSLATE)}$"), btn_tr_help)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TR_FA_EN)}$"), btn_tr_fa_en_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TR_EN_FA)}$"), btn_tr_en_fa_req)
    )

    # هندلر هواشناسی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_WEATHER)}$"), btn_weather_req)
    )

    # هندلر دانلود کتاب
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_BOOK)}$"), btn_book_req)
    )

    # هندلرهای منوی برنامه‌نویسی (این‌ها را قبل از MessageHandler مربوط به Stateها قرار دهید)
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_PROGRAMMING)}$"), btn_programming_menu
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_PROG_CHROME)}$"), btn_prog_chrome_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_PROG_FIREFOX)}$"), btn_prog_firefox_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_PROG_VSCODE)}$"), btn_prog_vscode_req
        )
    )

    # ثبت کال‌بک دکمه‌های شیشه‌ای (جستجوی کروم)
    application.add_handler(
        CallbackQueryHandler(handle_chrome_callback, pattern=r"^dlchrome_")
    )

    # هندلر پشتیبانی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_SUPPORT)}$"), btn_support_req)
    )
    # پردازش متون ارسالی کاربر بر اساس وضعیت (State) - همیشه باید آخرِ متن‌ها باشد
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, process_state_input)
    )

    # پردازش عکس‌ها (پشتیبانی همزمان از عکس عادی و عکسِ ارسال‌شده به صورت فایل)
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_photo_input)
    )
