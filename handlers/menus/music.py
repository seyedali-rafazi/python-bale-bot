from telegram import Update
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.keyboards import get_music_menu_keyboard
from handlers.ensure_membership import ensure_membership



async def btn_music_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    await update.message.reply_text(
        "🎵 به بخش موسیقی خوش آمدید!\nیک گزینه را انتخاب کنید 👇",
        reply_markup=get_music_menu_keyboard(),
    )


async def btn_music_track_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_track")
    await update.message.reply_text("🔍 نام آهنگ یا خواننده را بفرستید:")


async def btn_music_album_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_album")
    await update.message.reply_text("💿 نام آلبوم را برای جستجو بفرستید:")


async def btn_music_artist_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_artist")
    await update.message.reply_text("🎤 نام خواننده مورد نظر را بفرستید:")


async def btn_music_playlist_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_music_playlist")
    await update.message.reply_text("🎧 نام یا موضوع پلی‌لیست را بفرستید:")
