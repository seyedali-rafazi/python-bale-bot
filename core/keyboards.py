# core/keyboards.py

from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from .constants import *


def get_main_menu_keyboard():
    keyboard = [
        [
            KeyboardButton(BTN_PROFILE),
            KeyboardButton(BTN_CLOUD_STORAGE),
            KeyboardButton(BTN_BUY_VIP),
        ],
        [
            KeyboardButton(BTN_PROGRAMMING),
            KeyboardButton(BTN_GOOGLE_SEARCH),
        ],
        [KeyboardButton(BTN_DL_TIKTOK)],
        [KeyboardButton(BTN_DL_YOUTUBE)],
        [
            KeyboardButton(BTN_DL_INSTA),
            KeyboardButton(BTN_PINTEREST),
        ],
        [KeyboardButton(BTN_TRANSLATE), KeyboardButton(BTN_WEATHER)],
        [KeyboardButton(BTN_AI)],
        [KeyboardButton(BTN_TELEGRAM), KeyboardButton(BTN_MUSIC)],
        [KeyboardButton(BTN_SUPPORT)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_yt_format_keyboard():
    keyboard = [
        [KeyboardButton(BTN_YT_VIDEO)],
        [KeyboardButton(BTN_YT_AUDIO)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_ai_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_AI_CHAT), KeyboardButton(BTN_AI_OCR)],
        [KeyboardButton(BTN_AI_TTS), KeyboardButton(BTN_AI_IMAGE)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_music_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_MUSIC_TRACK), KeyboardButton(BTN_MUSIC_ALBUM)],
        [KeyboardButton(BTN_MUSIC_ARTIST), KeyboardButton(BTN_MUSIC_PLAYLIST)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_telegram_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_TG_SINGLE)],
        [KeyboardButton(BTN_TG_LATEST)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_youtube_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_YT_LAST5), KeyboardButton(BTN_YT_CH_SEARCH)],
        [KeyboardButton(BTN_YT_GLOBAL)],
        [KeyboardButton(BTN_YT_LINK_VID), KeyboardButton(BTN_YT_LINK_MP3)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_insta_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_IG_EXPLORE)],
        [KeyboardButton(BTN_IG_LINK_DL)],
        [KeyboardButton(BTN_IG_SEARCH), KeyboardButton(BTN_IG_TREND)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_translation_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_TR_FA_EN)],
        [KeyboardButton(BTN_TR_EN_FA)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_programming_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_PROG_GITHUB)],
        [KeyboardButton(BTN_PROG_CHROME), KeyboardButton(BTN_PROG_FIREFOX)],
        [KeyboardButton(BTN_PROG_VSCODE)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_tiktok_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_TT_EXPLORE)],
        [KeyboardButton(BTN_TT_LINK)],
        [KeyboardButton(BTN_TT_SEARCH), KeyboardButton(BTN_TT_TREND)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_github_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_GH_DL_REPO)],
        [KeyboardButton(BTN_GH_SEARCH), KeyboardButton(BTN_GH_USER)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_yt_quality_telegram_keyboard():
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("144p", callback_data="ytqual_144")],
            [InlineKeyboardButton("240p", callback_data="ytqual_240")],
            [InlineKeyboardButton("360p", callback_data="ytqual_360")],
            [InlineKeyboardButton("480p", callback_data="ytqual_480")],
            [InlineKeyboardButton("720p", callback_data="ytqual_720")],
        ]
    )
    return keyboard


def get_yt_quality_server_keyboard():
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("144p", callback_data="ytqual_144")],
            [InlineKeyboardButton("240p", callback_data="ytqual_240")],
            [InlineKeyboardButton("360p", callback_data="ytqual_360")],
            [InlineKeyboardButton("480p", callback_data="ytqual_480")],
            [InlineKeyboardButton("720p", callback_data="ytqual_720")],
        ]
    )
    return keyboard


def get_cloud_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_UPLOAD_TO_CLOUD)],
        [KeyboardButton(BTN_CLOUD_FILES)],
        [KeyboardButton(BTN_BUY_CLOUD)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_cloud_buy_keyboard():
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("5 GB", callback_data="cloud_buy_5gb")],
            [InlineKeyboardButton("10 GB", callback_data="cloud_buy_10gb")],
            [InlineKeyboardButton("20 GB", callback_data="cloud_buy_20gb")],
            [InlineKeyboardButton("50 GB", callback_data="cloud_buy_50gb")],
        ]
    )
    return keyboard


def get_google_search_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_GOOGLE_SEARCH_SUBJECT)],
        [KeyboardButton(BTN_GOOGLE_SEARCH_LINK)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
