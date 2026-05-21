# handlers/states/state_yt_archive.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.database import search_archive_by_title, search_archive_by_channel
from core.yt_moderation import (
    MSG_BLOCKED_SEARCH,
    MSG_BLOCKED_CHANNEL,
    is_search_query_blocked,
    check_channel_allowed,
)


async def handle_yt_archive_search_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
):
    if await is_search_query_blocked(text):
        await update.message.reply_text(MSG_BLOCKED_SEARCH)
        return

    if step == "waiting_yt_archive_search_title":
        results = await search_archive_by_title(text)
        empty_msg = "نتیجه‌ای برای این عنوان در کش مشترک پیدا نشد."
    else:
        if not await check_channel_allowed(text):
            await update.message.reply_text(MSG_BLOCKED_CHANNEL)
            return
        results = await search_archive_by_channel(text)
        empty_msg = "نتیجه‌ای برای این کانال در کش مشترک پیدا نشد."

    if not results:
        await update.message.reply_text(empty_msg)
        return

    keyboard = []
    lines = ["🔍 نتایج جستجو (جدیدترین انتشار در یوتیوب):\n"]
    for row in results[:12]:
        title = row["title"] or row["yt_video_id"] or "ویدیو"
        if len(title) > 45:
            title = title[:42] + "…"
        ch = row["channel_name"]
        lines.append(f"• {title}\n  📺 {ch}")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"▶️ {title[:30]}",
                    callback_data=f"ytarc_vid_{row['id']}",
                )
            ]
        )

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
