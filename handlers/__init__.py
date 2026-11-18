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
    btn_yt_my_cache_req,
    btn_yt_cache_search_title_req,
    btn_yt_cache_search_channel_req,
    yt_archive_callback,
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
    btn_music_identify_req,
    btn_pinterest_req,
    btn_tiktok_req,
    btn_tt_link_req,
    btn_tt_search_req,
    btn_tt_trend_req,
    btn_web_search_req,
    btn_google_search_subject_req,
    btn_google_search_link_req,
    btn_image_processing_menu,
    btn_img_create_pdf_req,
    btn_img_convert_format_req,
    btn_img_resize_req,
    btn_img_remove_bg_req,
    btn_img_video_to_gif_req,
    btn_img_extract_audio_req,
    btn_research_menu,
    btn_kaggle_menu,
    btn_kaggle_search_req,
    btn_kaggle_popular_req,
    btn_kaggle_dl_link_req,
    btn_book_menu,
    btn_book_search_req,
    btn_software_menu,
    btn_software_android_req,
    btn_software_windows_req,
)
from .states import process_state_input, process_photo_input, process_media_input
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
    cmd_addcloud,
    cmd_give_5gb_vips,
    cmd_fix_yt_cache,
    cmd_clean_yt_cache,
    cmd_channel_blacklist,
    cmd_blockword,
    cmd_monitor_report,
)
from .states.state_programming import handle_chrome_callback
from .states.state_music import handle_music_callback
from .states.state_insta import handle_insta_callback
from .payment import (
    accept_cloud_purchase_tos,
    btn_buy_vip,
    precheckout_callback,
    successful_payment_callback,
    handle_tos_acceptance,
)
from handlers.states.state_pinterest import handle_more_pins_callback
from handlers.states.youtube import (
    youtube_destination_callback,
    youtube_delivery_callback,
    youtube_quality_callback,
)
from handlers.states.state_github import github_callback_handler
from handlers.states.state_web_search import web_search_callback
from handlers.states.state_kaggle import kaggle_callback_handler
from handlers.states.state_book import book_callback_handler
from handlers.states.state_software import software_callback_handler

from .menus.cloud import (
    btn_buy_cloud_menu,
    btn_buy_cloud_size,
    btn_cloud_files,
    btn_cloud_storage_menu,
)
from handlers.states.state_cloud import (
    start_cloud_upload,
    handle_cloud_file_upload,
    cancel_cloud_upload,
    WAIT_FOR_FILE,
)


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
    application.add_handler(CommandHandler("addcloud", cmd_addcloud))
    application.add_handler(CommandHandler("give5gbvips", cmd_give_5gb_vips))
    application.add_handler(CommandHandler("fixytcache", cmd_fix_yt_cache))
    application.add_handler(CommandHandler("cleanytcache", cmd_clean_yt_cache))
    application.add_handler(CommandHandler("channelblacklist", cmd_channel_blacklist))
    application.add_handler(CommandHandler("blockword", cmd_blockword))
    application.add_handler(CommandHandler("monitor", cmd_monitor_report))

    # دستورات پایه
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("tr", cmd_tr))

    # جدول مسیریابی O(1) برای دکمه‌های ثابت منو (به جای بررسی خطی ۶۰+ Regex روی هر پیام)
    menu_button_handlers = {
        BTN_BACK: btn_back_action,
        BTN_DL_YOUTUBE: btn_yt_req,
        BTN_YT_MY_CACHE: btn_yt_my_cache_req,
        BTN_AI: btn_ai_menu,
        BTN_AI_CHAT: btn_ai_chat_req,
        BTN_AI_OCR: btn_ai_ocr_req,
        BTN_AI_TTS: btn_ai_tts_req,
        BTN_AI_IMAGE: btn_ai_image_req,
        BTN_TELEGRAM: btn_telegram_menu,
        BTN_TG_SINGLE: btn_tg_single_req,
        BTN_TG_LATEST: btn_tg_latest_req,
        BTN_YT_LAST5: btn_yt_last5_req,
        BTN_YT_CH_SEARCH: btn_yt_ch_search_req,
        BTN_YT_GLOBAL: btn_yt_global_req,
        BTN_YT_LINK_VID: btn_yt_link_vid_req,
        BTN_YT_LINK_MP3: btn_yt_link_mp3_req,
        BTN_YT_TOP_VIDEOS: btn_yt_top_videos_req,
        BTN_YT_CACHE_SEARCH_CHANNEL: btn_yt_cache_search_channel_req,
        BTN_YT_CACHE_SEARCH_TITLE: btn_yt_cache_search_title_req,
        BTN_DL_INSTA: btn_ig_req,
        BTN_IG_LINK_DL: btn_ig_link_dl_req,
        BTN_TRANSLATE: btn_tr_help,
        BTN_TR_FA_EN: btn_tr_fa_en_req,
        BTN_TR_EN_FA: btn_tr_en_fa_req,
        BTN_WEATHER: btn_weather_req,
        BTN_PROGRAMMING: btn_programming_menu,
        BTN_PROG_CHROME: btn_prog_chrome_req,
        BTN_PROG_FIREFOX: btn_prog_firefox_req,
        BTN_PROG_VSCODE: btn_prog_vscode_req,
        BTN_PROG_GITHUB: btn_prog_github_menu,
        BTN_GH_DL_REPO: btn_gh_dl_req,
        BTN_GH_USER: btn_gh_user_req,
        BTN_GH_SEARCH: btn_gh_search_req,
        BTN_MUSIC: btn_music_menu,
        BTN_MUSIC_TRACK: btn_music_track_req,
        BTN_MUSIC_ALBUM: btn_music_album_req,
        BTN_MUSIC_ARTIST: btn_music_artist_req,
        BTN_MUSIC_PLAYLIST: btn_music_playlist_req,
        BTN_MUSIC_IDENTIFY: btn_music_identify_req,
        BTN_BUY_VIP: btn_buy_vip,
        BTN_PINTEREST: btn_pinterest_req,
        BTN_GOOGLE_SEARCH: btn_web_search_req,
        BTN_GOOGLE_SEARCH_SUBJECT: btn_google_search_subject_req,
        BTN_GOOGLE_SEARCH_LINK: btn_google_search_link_req,
        BTN_IMAGE_PROCESSING: btn_image_processing_menu,
        BTN_IMG_CREATE_PDF: btn_img_create_pdf_req,
        BTN_IMG_CONVERT_FORMAT: btn_img_convert_format_req,
        BTN_IMG_RESIZE: btn_img_resize_req,
        BTN_IMG_REMOVE_BG: btn_img_remove_bg_req,
        BTN_MEDIA_VIDEO_TO_GIF: btn_img_video_to_gif_req,
        BTN_MEDIA_EXTRACT_AUDIO: btn_img_extract_audio_req,
        BTN_DL_TIKTOK: btn_tiktok_req,
        BTN_TT_LINK: btn_tt_link_req,
        BTN_TT_SEARCH: btn_tt_search_req,
        BTN_TT_TREND: btn_tt_trend_req,
        BTN_RESEARCH: btn_research_menu,
        BTN_KAGGLE: btn_kaggle_menu,
        BTN_KAGGLE_SEARCH: btn_kaggle_search_req,
        BTN_KAGGLE_POPULAR: btn_kaggle_popular_req,
        BTN_KAGGLE_DL_LINK: btn_kaggle_dl_link_req,
        BTN_BOOK_DOWNLOAD: btn_book_menu,
        BTN_BOOK_SEARCH: btn_book_search_req,
        BTN_SOFTWARE: btn_software_menu,
        BTN_SOFTWARE_ANDROID: btn_software_android_req,
        BTN_SOFTWARE_WINDOWS: btn_software_windows_req,
        BTN_SUPPORT: btn_support_req,
        BTN_PROFILE: btn_profile_req,
        BTN_CLOUD_STORAGE: btn_cloud_storage_menu,
    }

    async def dispatch_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.message.text or "").strip() if update.message else ""
        handler_fn = menu_button_handlers.get(text)
        if handler_fn is not None:
            await handler_fn(update, context)

    application.add_handler(
        MessageHandler(
            filters.Text(tuple(menu_button_handlers.keys())),
            dispatch_menu_button,
        )
    )

    # کال‌بک‌های یوتیوب و آرشیو
    application.add_handler(
        CallbackQueryHandler(youtube_destination_callback, pattern="^ytdest_")
    )
    application.add_handler(
        CallbackQueryHandler(youtube_delivery_callback, pattern="^ytdel_")
    )
    application.add_handler(
        CallbackQueryHandler(youtube_quality_callback, pattern="^ytqual_")
    )
    application.add_handler(
        CallbackQueryHandler(yt_archive_callback, pattern=r"^ytarc_")
    )

    # کال‌بک‌های برنامه‌نویسی، موسیقی، اینستاگرام، پینترست، وب، گیت‌هاب، کاگل، کتاب، نرم‌افزار
    application.add_handler(
        CallbackQueryHandler(handle_chrome_callback, pattern=r"^dlchrome_")
    )
    application.add_handler(
        CallbackQueryHandler(
            handle_music_callback,
            pattern=r"^(album_|playlist_|artist_|toptracks_|dltrack_)",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            handle_insta_callback,
            pattern=r"^ig_dl_",
        )
    )
    application.add_handler(
        CallbackQueryHandler(handle_more_pins_callback, pattern="^more_pins$")
    )
    application.add_handler(
        CallbackQueryHandler(web_search_callback, pattern=r"^webres_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(github_callback_handler, pattern=r"^ghdl_")
    )
    application.add_handler(
        CallbackQueryHandler(kaggle_callback_handler, pattern=r"^kgdl_")
    )
    application.add_handler(
        CallbackQueryHandler(book_callback_handler, pattern=r"^bookdl_")
    )
    application.add_handler(
        CallbackQueryHandler(software_callback_handler, pattern=r"^dl_soft_")
    )

    # هندلرهای پرداخت (فقط یک‌بار)
    application.add_handler(
        CallbackQueryHandler(handle_tos_acceptance, pattern="^accept_tos$")
    )
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )

    # Cloud upload conversation handler
    from telegram.ext import ConversationHandler

    cloud_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{re.escape(BTN_UPLOAD_TO_CLOUD)}$"), start_cloud_upload
            ),
            CallbackQueryHandler(start_cloud_upload, pattern="^cloud_upload$"),
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
        conversation_timeout=300,
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

    # Cloud purchase size handler (5/10/20/50 GB)
    async def handle_cloud_buy_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        match = re.match(r"^cloud_buy_(5|10|20|50)gb$", query.data or "")
        if match:
            await btn_buy_cloud_size(update, context, int(match.group(1)))

    application.add_handler(
        CallbackQueryHandler(handle_cloud_buy_size, pattern=r"^cloud_buy_(5|10|20|50)gb$")
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

    # پردازش ویس / صوت / ویدیو (تشخیص آهنگ و ...) — فقط چت خصوصی
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & (filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE),
            process_media_input,
        )
    )

    # پردازش متون ارسالی کاربر بر اساس وضعیت (State) - فقط چت خصوصی
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            process_state_input,
        )
    )

    # پردازش عکس‌ها — فقط چت خصوصی
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.PHOTO | filters.Document.IMAGE),
            process_photo_input,
        )
    )
