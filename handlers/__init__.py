# handlers/__init__.py

import re
from telegram.ext import MessageHandler, CommandHandler, filters
from core.constants import *
from .commands import cmd_start, cmd_book, cmd_tr, cmd_weather
from .menus import (
    btn_book_help, btn_tr_help, btn_weather_help, 
    btn_yt_req, btn_ig_req, btn_back_action,
    btn_ai_menu, btn_ai_chat_req, btn_ai_ocr_req,
    btn_ai_tts_req, btn_ai_image_req,
    btn_music_menu, btn_music_search_req, btn_spotify_req,
    btn_telegram_menu, btn_tg_single_req, btn_tg_latest_req
)
from .states import process_state_input, process_photo_input 
from core.admin import cmd_stats, cmd_setvip

def register_all_handlers(application):
    # دستورات ادمین
    application.add_handler(CommandHandler('stats', cmd_stats))
    application.add_handler(CommandHandler('setvip', cmd_setvip))

    # دستورات پایه
    application.add_handler(CommandHandler('start', cmd_start))
    application.add_handler(CommandHandler('book', cmd_book))
    application.add_handler(CommandHandler('tr', cmd_tr))
    application.add_handler(CommandHandler('weather', cmd_weather))

    # دکمه‌های بازگشت
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_BACK)}$"), btn_back_action))

    # دکمه‌های منوی اصلی
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_BOOK)}$"), btn_book_help))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_TRANSLATE)}$"), btn_tr_help))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_WEATHER)}$"), btn_weather_help))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_DL_YOUTUBE)}$"), btn_yt_req))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_DL_INSTA)}$"), btn_ig_req))
    
    # هندلرهای هوش مصنوعی 
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_AI)}$"), btn_ai_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_CHAT)}$"), btn_ai_chat_req))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_OCR)}$"), btn_ai_ocr_req))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_TTS)}$"), btn_ai_tts_req))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_IMAGE)}$"), btn_ai_image_req))

    # هندلرهای موسیقی (این بخش به اینجا منتقل شد!)
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_MUSIC)}$"), btn_music_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_MUSIC_SEARCH)}$"), btn_music_search_req))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_MUSIC_SPOTIFY)}$"), btn_spotify_req))

    #هندلز های تلگرام
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_TELEGRAM)}$"), btn_telegram_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_TG_SINGLE)}$"), btn_tg_single_req))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_TG_LATEST)}$"), btn_tg_latest_req))

    # پردازش متون ارسالی کاربر بر اساس وضعیت (State) - همیشه باید آخرِ متن‌ها باشد
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_state_input))
    
    # پردازش عکس‌ها (پشتیبانی همزمان از عکس عادی و عکسِ ارسال‌شده به صورت فایل)
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_photo_input))
