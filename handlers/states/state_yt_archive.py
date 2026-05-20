# handlers/states/state_yt_archive.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.database import search_archive_by_title, search_archive_by_channel


async def handle_yt_archive_search_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
):
    if step == "waiting_yt_archive_search_title":
        results = await search_archive_by_title(text)
        empty_msg = "نتیجه‌ای برای این عنوان در کش مشترک پیدا نشد."
    else:
        results = await search_archive_by_channel(text)
        empty_msg = "نتیجه‌ای برای این کانال در کش مشترک پیدا نشد."

    if not results:
        await update.message.reply_text(empty_msg)
        return

    keyboard = []
    lines = ["🔍 نتایج جستجو (جدیدترین اول):\n"]
    for row in results[:12]:
        title = row["title"]
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
