# core/keyboards.py

from telegram import ReplyKeyboardMarkup, KeyboardButton
from .constants import *


def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_DL_YOUTUBE), KeyboardButton(BTN_DL_INSTA)],
        [KeyboardButton(BTN_TRANSLATE), KeyboardButton(BTN_WEATHER)],
        [KeyboardButton(BTN_BOOK), KeyboardButton(BTN_AI)],
        [KeyboardButton(BTN_TELEGRAM), KeyboardButton(BTN_MUSIC)],
        [KeyboardButton(BTN_PROGRAMMING)],
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
        [KeyboardButton(BTN_MUSIC_SEARCH)],
        [KeyboardButton(BTN_MUSIC_SPOTIFY)],
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
        [KeyboardButton(BTN_PROG_CHROME), KeyboardButton(BTN_PROG_FIREFOX)],
        [KeyboardButton(BTN_PROG_VSCODE), KeyboardButton(BTN_PROG_DOCS)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
