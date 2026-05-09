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
        [KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_BUY_VIP)],
        [KeyboardButton(BTN_PROGRAMMING)],
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
    keyboard = [[BTN_IG_LINK_DL], [BTN_BACK]]
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


# core/keyboards.py


def get_main_menu_article():
    keyboard = [
        [KeyboardButton(BTN_ARTICLE)],
        [KeyboardButton(BTN_BOOK_SEARCH)],
        [KeyboardButton(BTN_SMART_ABSTRACT), KeyboardButton(BTN_CITATION)],
        [KeyboardButton(BTN_BIBTEX)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_article_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_SEARCH_DOI)],
        [KeyboardButton(BTN_SEARCH_NAME)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_citation_format_keyboard():
    keyboard = [
        [KeyboardButton(BTN_APA), KeyboardButton(BTN_IEEE)],
        [KeyboardButton(BTN_HARVARD)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_year_filter_keyboard():
    keyboard = [
        [KeyboardButton(BTN_YEAR_ALL)],
        [KeyboardButton(BTN_YEAR_2015), KeyboardButton(BTN_YEAR_2020)],
        [KeyboardButton(BTN_YEAR_2024)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_sort_filter_keyboard():
    keyboard = [
        [KeyboardButton(BTN_SORT_RELEVANCE)],
        [KeyboardButton(BTN_SORT_CITATION)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_books_inline_keyboard(books_count: int):
    keyboard = []
    row = []
    for i in range(books_count):
        # دکمه ها با نام 📥 1, 📥 2 و ...
        row.append(InlineKeyboardButton(f"📥 {i + 1}", callback_data=f"dlbook_{i}"))
        if len(row) == 4:  # هر ردیف ۴ دکمه
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)
