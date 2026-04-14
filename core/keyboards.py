# core/keyboards.py 

from telegram import ReplyKeyboardMarkup, KeyboardButton
from .constants import *

def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_DL_YOUTUBE), KeyboardButton(BTN_DL_INSTA)],
        [KeyboardButton(BTN_TRANSLATE), KeyboardButton(BTN_WEATHER)],
        [KeyboardButton(BTN_BOOK), KeyboardButton(BTN_AI)] 
        [KeyboardButton(BTN_MUSIC)] 
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_yt_format_keyboard():
    keyboard = [
        [KeyboardButton(BTN_YT_VIDEO)],
        [KeyboardButton(BTN_YT_AUDIO)],
        [KeyboardButton(BTN_BACK)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_ai_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_AI_CHAT), KeyboardButton(BTN_AI_OCR)],
        [KeyboardButton(BTN_AI_TTS), KeyboardButton(BTN_AI_IMAGE)],
        [KeyboardButton(BTN_BACK)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_music_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_MUSIC_SEARCH)],
        [KeyboardButton(BTN_MUSIC_SPOTIFY)],
        [KeyboardButton(BTN_BACK)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)