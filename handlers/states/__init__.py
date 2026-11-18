# handlers/states/__init__.py

import time

from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import async_get_state
from .state_programming import handle_programming_state
from .youtube import handle_youtube_state
from .state_insta import handle_insta_state
from .state_ai import handle_ai_state, handle_ai_photo
from .state_music import handle_music_state, handle_music_identify_media
from .state_telegram import handle_telegram_state
from .state_translation import handle_translation_state
from .state_weather import handle_weather_state
from .state_pinterest import handle_pinterest_state
from .state_tiktok import handle_tiktok_state
from .state_github import handle_github_state
from .state_web_search import handle_web_search_state
from .state_yt_archive import handle_yt_archive_search_state
from .state_image_processing import (
    handle_img_create_pdf,
    handle_img_convert_format,
    handle_img_resize,
    handle_img_remove_bg,
    handle_img_video_to_gif,
    handle_img_extract_audio,
)
from .state_kaggle import handle_kaggle_state
from .state_book import handle_book_state
from .state_software import handle_software_state, software_callback_handler

_MENU_HINT_COOLDOWN_SEC = 3.0
_MAX_MENU_HINT_ENTRIES = 5000
_last_menu_hint_at: dict[str, float] = {}

_BOT_OWN_REPLIES = frozenset(
    {
        "لطفاً از منو استفاده کنید.",
        "متوجه نشدم. لطفاً از منو استفاده کنید.",
    }
)


def _is_human_message(update: Update) -> bool:
    chat = update.effective_chat
    if chat is None or chat.type != "private":
        return False
    user = update.effective_user
    if user is None or user.is_bot:
        return False
    if update.message is None:
        return False
    return True


async def _reply_menu_hint(
    update: Update,
    text: str = "لطفاً از منو استفاده کنید.",
) -> None:
    chat_id = str(update.effective_chat.id)
    now = time.monotonic()
    if now - _last_menu_hint_at.get(chat_id, 0.0) < _MENU_HINT_COOLDOWN_SEC:
        return
    if len(_last_menu_hint_at) >= _MAX_MENU_HINT_ENTRIES:
        cutoff = now - _MENU_HINT_COOLDOWN_SEC
        stale = [k for k, ts in _last_menu_hint_at.items() if ts < cutoff]
        for k in stale:
            _last_menu_hint_at.pop(k, None)
        if len(_last_menu_hint_at) >= _MAX_MENU_HINT_ENTRIES:
            _last_menu_hint_at.clear()
    _last_menu_hint_at[chat_id] = now
    await update.message.reply_text(text)


async def process_state_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_human_message(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Commands are handled by CommandHandler; Bale may omit bot_command entities.
    if text.startswith("/"):
        return

    if text in _BOT_OWN_REPLIES:
        return

    chat_id = str(update.effective_chat.id)
    state_data = await async_get_state(chat_id)
    step = state_data.get("step")

    # بازگشت سریع به منو
    if text in ["0", "لغو", "شروع"]:
        from handlers.commands import cmd_start  # ایمپورت از یک سطح بالاتر

        await cmd_start(update, context)
        return

    if not step:
        await _reply_menu_hint(update)
        return

    # 🌟 مسیریابی بر اساس نام step (جدول O(1) دقیق + جدول پیشوند مرتب‌شده)
    exact_handler = _EXACT_TEXT_HANDLERS.get(step)
    if exact_handler is not None:
        await exact_handler(update, context)
        return

    if step in ("waiting_music_search", "waiting_spotify_link"):
        await handle_music_state(update, context, step, text, chat_id, state_data)
        return

    for prefix, handler_fn in _PREFIX_TEXT_HANDLERS:
        if step.startswith(prefix):
            await handler_fn(update, context, step, text, chat_id, state_data)
            return


_EXACT_TEXT_HANDLERS = {
    "img_create_pdf": handle_img_create_pdf,
    "img_convert_format": handle_img_convert_format,
    "img_resize": handle_img_resize,
    "img_remove_bg": handle_img_remove_bg,
    "img_video_to_gif": handle_img_video_to_gif,
    "img_extract_audio": handle_img_extract_audio,
}


async def _handle_yt_archive_wrap(update, context, step, text, chat_id, _state_data):
    await handle_yt_archive_search_state(update, context, step, text, chat_id)


async def _handle_pinterest_wrap(update, context, _step, text, chat_id, _state_data):
    await handle_pinterest_state(update, context, text, chat_id)


async def _handle_web_search_wrap(update, context, _step, text, chat_id, state_data):
    await handle_web_search_state(update, context, text, chat_id, state_data=state_data)


_PREFIX_TEXT_HANDLERS = (
    ("waiting_yt_archive_", _handle_yt_archive_wrap),
    ("waiting_yt", handle_youtube_state),
    ("waiting_ig", handle_insta_state),
    ("waiting_ai", handle_ai_state),
    ("waiting_tg", handle_telegram_state),
    ("waiting_tr", handle_translation_state),
    ("waiting_weather", handle_weather_state),
    ("waiting_prog", handle_programming_state),
    ("waiting_music_", handle_music_state),
    ("waiting_pinterest", _handle_pinterest_wrap),
    ("waiting_tt", handle_tiktok_state),
    ("waiting_gh", handle_github_state),
    ("waiting_google_search", _handle_web_search_wrap),
    ("waiting_kaggle", handle_kaggle_state),
    ("waiting_book", handle_book_state),
    ("waiting_software_", handle_software_state),
)


async def process_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_human_message(update):
        return

    chat_id = str(update.effective_chat.id)
    state_data = await async_get_state(chat_id)
    step = state_data.get("step") if state_data else None

    if step == "waiting_ai_ocr":
        await handle_ai_photo(update, context, chat_id)
    elif step == "waiting_ai_chat":
        await update.message.reply_text(
            "❌ دستیار هوشمند فقط متن می‌پذیرد.\n"
            "لطفاً سوال خود را به صورت پیام متنی بنویسید."
        )
    elif step == "img_create_pdf":
        await handle_img_create_pdf(update, context)
    elif step == "img_convert_format":
        await handle_img_convert_format(update, context)
    elif step == "img_resize":
        await handle_img_resize(update, context)
    elif step == "img_remove_bg":
        await handle_img_remove_bg(update, context)
    else:
        await _reply_menu_hint(update, "متوجه نشدم. لطفاً از منو استفاده کنید.")


async def process_media_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_human_message(update):
        return

    chat_id = str(update.effective_chat.id)
    state_data = await async_get_state(chat_id)
    step = state_data.get("step") if state_data else None

    if step == "waiting_music_identify":
        await handle_music_identify_media(update, context)
    elif step == "img_video_to_gif":
        await handle_img_video_to_gif(update, context)
    elif step == "img_extract_audio":
        await handle_img_extract_audio(update, context)
    elif step == "waiting_ai_chat":
        await update.message.reply_text(
            "❌ دستیار هوشمند فقط متن می‌پذیرد.\n"
            "صدا، ویدیو و فایل در این بخش پشتیبانی نمی‌شود."
        )
    else:
        await _reply_menu_hint(update, "متوجه نشدم. لطفاً از منو استفاده کنید.")
