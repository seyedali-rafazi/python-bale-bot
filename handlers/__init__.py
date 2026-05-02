# handlers/__init__.py

import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    MessageHandler,
    CommandHandler,
    filters,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    TypeHandler,
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
    btn_profile_req,
    btn_music_menu,
    btn_music_track_req,
    btn_music_album_req,
    btn_music_artist_req,
    btn_music_playlist_req,
)
from .states import process_state_input, process_photo_input
from core.admin import (
    cmd_stats,
    cmd_setvip,
    cmd_messageuser,
    cmd_reset_limits,
    cmd_toggle_yt,
)
import os
from dotenv import load_dotenv
from .states.state_programming import handle_chrome_callback
from .states.state_music import handle_music_callback
from .payment import btn_buy_vip, precheckout_callback, successful_payment_callback


load_dotenv()
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_URL = os.getenv("CHANNEL_URL")


async def check_membership_middleware(update: Update, context):
    # توقف پردازش پیام‌های کانال (جلوگیری از لوپ)
    if update.channel_post or getattr(update.effective_chat, "type", "") == "channel":
        raise ApplicationHandlerStop()

    # اگر آپدیت یوزر نداشت کاری نکن
    if not update.effective_user:
        return

    # چک کردن فقط در پی‌وی ربات انجام شود
    if getattr(update.effective_chat, "type", "") != "private":
        return

    # اگر آیدی کانال تنظیم نشده بود، کاری نکن
    if not CHANNEL_ID:
        return

    user_id = update.effective_user.id
    is_member = False

    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            is_member = True
    except Exception:
        # اگر اروری رخ داد (مثل User not found)، یعنی کاربر در کانال نیست
        is_member = False

    if is_member:
        return  # کاربر عضو است، ادامه کار ربات

    # --- اگر به اینجا رسیدیم یعنی کاربر عضو نیست ---
    keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_URL)]]
    msg = "🛑 کاربر عزیز، برای استفاده از ربات حتماً باید در کانال ما عضو شوید.\n\nپس از عضویت، لطفاً دوباره تلاش کنید."

    if update.callback_query:
        await update.callback_query.answer("باید در کانال عضو شوید!", show_alert=True)
        await context.bot.send_message(
            chat_id=user_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.message:
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # متوقف کردن ادامه پردازش (تا ربات کار دیگری نکند)
    raise ApplicationHandlerStop()


def register_all_handlers(application):
    # این خط باعث می‌شود قبل از هر دستوری، جوین اجباری چک شود (گروه 1-)
    application.add_handler(TypeHandler(Update, check_membership_middleware), group=-1)

    # دستورات ادمین
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("setvip", cmd_setvip))
    application.add_handler(CommandHandler("messageuser", cmd_messageuser))
    application.add_handler(CommandHandler("resetlimits", cmd_reset_limits))
    application.add_handler(CommandHandler("toggle_yt", cmd_toggle_yt))

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

    # هندلرهای منوی برنامه‌نویسی
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

    # هندلرهای موسیقی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_MUSIC)}$"), btn_music_menu)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_MUSIC_TRACK)}$"), btn_music_track_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_MUSIC_ALBUM)}$"), btn_music_album_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_MUSIC_ARTIST)}$"), btn_music_artist_req
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_MUSIC_PLAYLIST)}$"), btn_music_playlist_req
        )
    )

    # ثبت کال‌بک دکمه‌های شیشه‌ای مربوط به موسیقی
    application.add_handler(
        CallbackQueryHandler(
            handle_music_callback,
            pattern=r"^(album_|playlist_|artist_|toptracks_|dltrack_)",
        )
    )

    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_BUY_VIP)}$"), btn_buy_vip)
    )
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )
    # هندلر پشتیبانی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_SUPPORT)}$"), btn_support_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_PROFILE)}$"), btn_profile_req)
    )

    # پردازش متون ارسالی کاربر بر اساس وضعیت (State) - فقط چت خصوصی
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            process_state_input,
        )
    )

    # پردازش عکس‌ها - فقط چت خصوصی
    application.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.Document.IMAGE) & filters.ChatType.PRIVATE,
            process_photo_input,
        )
    )
