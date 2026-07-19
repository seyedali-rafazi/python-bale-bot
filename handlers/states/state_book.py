# handlers/states/state_book.py
"""
Book download state handler.

Flow:
  1. User types a search query  →  show inline result buttons.
  2. User taps a result button  →  download PDF from Internet Archive
                                    →  send as document.

Callback data format: bookdl_<ia_id>
"""

import asyncio
import logging
import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.state_manager import clear_state
from services.book import search_books, download_book, format_book_info

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# State handler — called from states/__init__.py
# ──────────────────────────────────────────────────────────────────────────────
async def handle_book_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_book_search":
        await _handle_book_search(update, context, text, chat_id)


async def _handle_book_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
    chat_id: str,
):
    clear_state(chat_id)
    msg = await update.message.reply_text(f"🔍 در حال جستجوی «{query}» در کتابخانه...")

    try:
        books = await search_books(query, max_results=8)
    except Exception:
        logger.exception("Book search failed for query: %s", query)
        await msg.edit_text("❌ خطا در ارتباط با سرور Open Library. لطفاً دوباره تلاش کنید.")
        return

    if not books:
        await msg.edit_text("❌ کتابی برای این جستجو یافت نشد. کلمات کلیدی دیگری امتحان کنید.")
        return

    # Build result text + inline keyboard
    result_text = f"📚 *نتایج جستجوی «{query}»:*\n\n"
    keyboard = []

    for i, book in enumerate(books, 1):
        result_text += f"{i}. {format_book_info(book)}\n\n"
        title_short = book["title"][:38]

        if book["has_pdf"]:
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {title_short}",
                    callback_data=f"bookdl_{book['ia_id']}",
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {title_short} (فایل موجود نیست)",
                    callback_data="bookdl_unavailable",
                )
            ])

    await msg.edit_text(result_text, parse_mode="Markdown")
    await update.message.reply_text(
        "👇 برای دانلود روی کتاب مورد نظر کلیک کنید:\n"
        "_(کتاب‌های با آیکون 🔒 فایل دانلودی ندارند)_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Callback handler — inline ⬇️ download buttons (pattern: ^bookdl_)
# ──────────────────────────────────────────────────────────────────────────────
async def book_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles tap on a book download inline button."""
    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. "bookdl_someia_id"
    chat_id = str(query.message.chat_id)

    if data == "bookdl_unavailable":
        await query.message.reply_text(
            "🔒 این کتاب فایل دانلودی رایگان ندارد.\n"
            "می‌توانید آن را مستقیماً در سایت Open Library جستجو کنید:\n"
            "https://openlibrary.org"
        )
        return

    ia_id = data.replace("bookdl_", "", 1)

    # Disable button to prevent double-tap
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await query.message.reply_text(
        f"⏳ در حال دانلود کتاب از Internet Archive...\n"
        f"🔖 شناسه: `{ia_id}`\n"
        f"این ممکن است چند ثانیه طول بکشد.",
        parse_mode="Markdown",
    )

    # Download in a thread-safe temp directory
    with tempfile.TemporaryDirectory(prefix="book_dl_") as tmp_dir:
        try:
            file_path = await download_book(ia_id, tmp_dir)
        except Exception:
            logger.exception("Book download failed: ia_id=%s", ia_id)
            await context.bot.send_message(
                chat_id,
                "❌ خطا در دانلود کتاب. لطفاً دوباره تلاش کنید.",
            )
            return

        if file_path is None:
            await context.bot.send_message(
                chat_id,
                "❌ فایل این کتاب در دسترس نیست یا حجم آن بیش از ۱۸ مگابایت است.\n"
                "می‌توانید آن را مستقیماً از:\n"
                f"https://archive.org/details/{ia_id}\n"
                "دانلود کنید.",
            )
            return

        # Send the file
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        caption = (
            f"📖 *کتاب دانلود شد*\n"
            f"📦 حجم: {file_size_mb:.1f} مگابایت\n"
            f"🌐 منبع: archive.org/details/{ia_id}"
        )
        try:
            with open(file_path, "rb") as fh:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=fh,
                    filename=os.path.basename(file_path),
                    caption=caption,
                    parse_mode="Markdown",
                )
            await context.bot.send_message(
                chat_id,
                "✅ کتاب با موفقیت ارسال شد!\n"
                "برای جستجوی کتاب دیگر دوباره دکمه 🔍 جستجوی کتاب را بزنید.",
            )
        except Exception:
            logger.exception("Failed to send book file: %s", file_path)
            await context.bot.send_message(
                chat_id,
                "❌ خطا در ارسال فایل. لطفاً دوباره تلاش کنید.",
            )
