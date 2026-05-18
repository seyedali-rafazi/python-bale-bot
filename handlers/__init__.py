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
    ContextTypes,
)
from core.constants import *
from .commands import cmd_start, cmd_tr
from .menus import (
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
    btn_yt_top_videos_req,
    btn_tr_help,
    btn_tr_fa_en_req,
    btn_tr_en_fa_req,
    btn_support_req,
    btn_programming_menu,
    btn_prog_chrome_req,
    btn_prog_firefox_req,
    btn_prog_vscode_req,
    btn_prog_github_menu,
    btn_gh_dl_req,
    btn_gh_user_req,
    btn_gh_search_req,
    btn_profile_req,
    btn_music_menu,
    btn_music_track_req,
    btn_music_album_req,
    btn_music_artist_req,
    btn_music_playlist_req,
    btn_pinterest_req,
    btn_tiktok_req,
    btn_tt_link_req,
    btn_tt_search_req,
    btn_tt_trend_req,
    btn_tt_explore_req,
    btn_web_search_req,
    btn_google_search_subject_req,
    btn_google_search_link_req,
)
from .states import process_state_input, process_photo_input
from core.admin import (
    cmd_stats,
    cmd_setvip,
    cmd_setexpire,
    cmd_userinfo,
    cmd_messageuser,
    cmd_reset_limits,
    cmd_toggle_yt,
    cmd_resetuser,
    cmd_addvip_all,
    cmd_give_5gb_vips,
)
import os
from dotenv import load_dotenv
from .states.state_programming import handle_chrome_callback
from .states.state_music import handle_music_callback
from .states.state_insta import handle_insta_callback
from .payment import (
    btn_buy_vip,
    precheckout_callback,
    successful_payment_callback,
    handle_tos_acceptance,
)
from handlers.states.state_pinterest import handle_more_pins_callback
from handlers.states.youtube import (
    youtube_destination_callback,
    youtube_quality_callback,
)
from handlers.states.state_github import github_callback_handler
from handlers.states.state_web_search import web_search_callback

from .menus.cloud import btn_cloud_storage_menu
from handlers.states.state_cloud import (
    start_cloud_upload,
    handle_cloud_file_upload,
    cancel_cloud_upload,
    WAIT_FOR_FILE,
)
from .menus.cloud import (
    btn_buy_cloud_menu,
    btn_cloud_files,
    btn_buy_cloud_size,
)
from .payment import (
    accept_cloud_purchase_tos,
)


load_dotenv()
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_URL = os.getenv("CHANNEL_URL")


def register_all_handlers(application):

    # دستورات ادمین
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("setvip", cmd_setvip))
    application.add_handler(CommandHandler("setexpire", cmd_setexpire))
    application.add_handler(CommandHandler("userinfo", cmd_userinfo))
    application.add_handler(CommandHandler("messageuser", cmd_messageuser))
    application.add_handler(CommandHandler("resetlimits", cmd_reset_limits))
    application.add_handler(CommandHandler("limit_yt", cmd_toggle_yt))
    application.add_handler(CommandHandler("resetuser", cmd_resetuser))
    application.add_handler(CommandHandler("addvipall", cmd_addvip_all))
    application.add_handler(CommandHandler("give5gbvips", cmd_give_5gb_vips))

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
    application.add_handler(
        CallbackQueryHandler(youtube_destination_callback, pattern="^ytdest_")
    )
    application.add_handler(
        CallbackQueryHandler(youtube_quality_callback, pattern="^ytqual_")
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_YT_TOP_VIDEOS)}$"), btn_yt_top_videos_req
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

    # --- کدهای جدید گیت‌هاب ---
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_PROG_GITHUB)}$"), btn_prog_github_menu
        )
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_GH_DL_REPO)}$"), btn_gh_dl_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_GH_USER)}$"), btn_gh_user_req)
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

    # ثبت کال‌بک دکمه‌های شیشه‌ای مربوط به اینستاگرام
    application.add_handler(
        CallbackQueryHandler(
            handle_insta_callback,
            pattern=r"^(ig_dl_|ig_last_)",
        )
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_BUY_VIP)}$"), btn_buy_vip)
    )
    application.add_handler(
        CallbackQueryHandler(handle_tos_acceptance, pattern="^accept_tos$")
    )
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )

    # هندلر های پینترست
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_PINTEREST)}$"), btn_pinterest_req
        )
    )
    application.add_handler(
        CallbackQueryHandler(handle_more_pins_callback, pattern="^more_pins$")
    )

    # هندلرهای جست جو وب
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_GOOGLE_SEARCH)}$"), btn_web_search_req
        )
    )

    # هندلرهای دکمه‌های منوی جستجوی وب
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_GOOGLE_SEARCH_SUBJECT)}$"),
            btn_google_search_subject_req,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_GOOGLE_SEARCH_LINK)}$"),
            btn_google_search_link_req,
        )
    )

    # اضافه کردن کال‌بک دکمه‌های نتایج جستجو
    application.add_handler(
        CallbackQueryHandler(web_search_callback, pattern=r"^webres_\d+$")
    )

    # هندلر های تیک تاک
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_DL_TIKTOK)}$"), btn_tiktok_req)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TT_LINK)}$"), btn_tt_link_req)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_TT_SEARCH)}$"), btn_tt_search_req
        )
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_TT_TREND)}$"), btn_tt_trend_req)
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_TT_EXPLORE)}$"), btn_tt_explore_req
        )
    )
    application.add_handler(
        CallbackQueryHandler(github_callback_handler, pattern=r"^ghdl_")
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_GH_SEARCH)}$"), btn_gh_search_req
        )
    )

    # هندلر های پرداخت
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_BUY_VIP)}$"), btn_buy_vip)
    )
    application.add_handler(
        CallbackQueryHandler(handle_tos_acceptance, pattern="^accept_tos$")
    )
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )

    # هندلر پشتیبانی
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_SUPPORT)}$"), btn_support_req)
    )

    application.add_handler(MessageHandler(filters.Text(BTN_PROFILE), btn_profile_req))

    # هندلر ذخیره ابری
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(BTN_CLOUD_STORAGE)}$"), btn_cloud_storage_menu
        )
    )

    # Cloud upload conversation handler
    from telegram.ext import ConversationHandler

    cloud_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{re.escape(BTN_UPLOAD_TO_CLOUD)}$"), start_cloud_upload
            )
        ],
        states={
            WAIT_FOR_FILE: [
                MessageHandler(
                    filters.Document.ALL
                    | filters.VIDEO
                    | filters.AUDIO
                    | filters.PHOTO,
                    handle_cloud_file_upload,
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_cloud_upload)],
    )
    application.add_handler(cloud_conv)

    # Cloud storage callback handlers
    application.add_handler(
        CallbackQueryHandler(btn_cloud_storage_menu, pattern="^cloud_storage$")
    )
    application.add_handler(
        CallbackQueryHandler(btn_buy_cloud_menu, pattern="^cloud_buy_menu$")
    )
    application.add_handler(
        CallbackQueryHandler(btn_cloud_files, pattern="^cloud_files$")
    )

    # Back to cloud menu handler
    async def handle_cloud_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await btn_cloud_storage_menu(update, context)

    application.add_handler(
        CallbackQueryHandler(handle_cloud_back, pattern="^cloud_back$")
    )

    # Cloud purchase size handlers
    async def handle_cloud_buy_5gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await btn_buy_cloud_size(update, context, 5)

    async def handle_cloud_buy_10gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await btn_buy_cloud_size(update, context, 10)

    async def handle_cloud_buy_20gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await btn_buy_cloud_size(update, context, 20)

    async def handle_cloud_buy_50gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await btn_buy_cloud_size(update, context, 50)

    application.add_handler(
        CallbackQueryHandler(handle_cloud_buy_5gb, pattern="^cloud_buy_5gb$")
    )
    application.add_handler(
        CallbackQueryHandler(handle_cloud_buy_10gb, pattern="^cloud_buy_10gb$")
    )
    application.add_handler(
        CallbackQueryHandler(handle_cloud_buy_20gb, pattern="^cloud_buy_20gb$")
    )
    application.add_handler(
        CallbackQueryHandler(handle_cloud_buy_50gb, pattern="^cloud_buy_50gb$")
    )

    # Cloud purchase TOS acceptance
    async def handle_cloud_purchase_tos(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        match = re.search(r"accept_cloud_purchase_(\d+)", query.data)
        if match:
            size_gb = int(match.group(1))
            await accept_cloud_purchase_tos(update, context, size_gb)

    application.add_handler(
        CallbackQueryHandler(
            handle_cloud_purchase_tos, pattern=r"^accept_cloud_purchase_\d+$"
        )
    )

    # Back to main menu handler
    async def handle_back_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await cmd_start(update, context)

    application.add_handler(
        CallbackQueryHandler(handle_back_main_menu, pattern="^back_main_menu$")
    )

    # Cloud upload start handler (from callback)
    async def handle_cloud_upload_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        await start_cloud_upload(update, context)

    application.add_handler(
        CallbackQueryHandler(handle_cloud_upload_callback, pattern="^cloud_upload$")
    )

    # پردازش متون ارسالی کاربر بر اساس وضعیت (State) - همیشه باید آخرِ متن‌ها باشد
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, process_state_input)
    )

    # پردازش عکس‌ها (پشتیبانی همزمان از عکس عادی و عکسِ ارسال‌شده به صورت فایل)
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_photo_input)
    )
