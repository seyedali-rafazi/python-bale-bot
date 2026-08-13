# handlers/states/state_book.py
"""
Book download state handler.

Flow:
  1. User types a search query  →  show inline result buttons.
  2. User taps a result button  →  download from one of 4 sources
                                   →  send as document.

Book data is stored in context.bot_data["books"][chat_id] keyed by index
so the callback can retrieve the full book dict without encoding it in callback_data.

Callback data format: bookdl_<chat_id>_<index>
"""

import asyncio
import logging
import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.state_manager import clear_state
from core.database import log_upload_success, log_upload_failed
from services.book import search_books, download_book, format_book_info, SOURCE_LABELS

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
    msg = await update.message.reply_text(
        f"🔍 در حال جستجوی «{query}» در ۴ کتابخانه دیجیتال...\n"
        "⏳ لطفاً چند ثانیه صبر کنید."
    )

    try:
        books = await search_books(query, max_results=8)
    except Exception:
        logger.exception("Book search failed for query: %s", query)
        await msg.edit_text("❌ خطا در جستجو. لطفاً دوباره تلاش کنید.")
        await log_upload_failed("book", chat_id)
        return

    if not books:
        await msg.edit_text("❌ کتابی برای این جستجو یافت نشد. کلمات کلیدی دیگری امتحان کنید.")
        return

    # Store books in bot_data so callback can retrieve them
    if "books" not in context.bot_data:
        context.bot_data["books"] = {}
    context.bot_data["books"][chat_id] = books

    # Build result text + inline keyboard
    result_text = f"📚 *نتایج جستجوی «{query}»:*\n\n"
    keyboard = []

    for i, book in enumerate(books):
        result_text += f"{i + 1}. {format_book_info(book)}\n\n"
        title_short = book["title"][:35]

        if book["has_file"]:
            ext_tag = book.get("file_ext", ".epub").lstrip(".").upper()
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {title_short} [{ext_tag}]",
                    callback_data=f"bookdl_{chat_id}_{i}",
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {title_short} (بدون فایل)",
                    callback_data="bookdl_unavailable",
                )
            ])

    try:
        await msg.edit_text(result_text, parse_mode="Markdown")
    except Exception:
        await msg.delete()
        await update.message.reply_text(result_text, parse_mode="Markdown")

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

    data    = query.data
    chat_id = str(query.message.chat_id)

    if data == "bookdl_unavailable":
        await query.message.reply_text(
            "🔒 این کتاب فایل دانلودی رایگان ندارد.\n"
            "می‌توانید آن را مستقیماً جستجو کنید:\n"
            "• https://www.gutenberg.org\n"
            "• https://openlibrary.org\n"
            "• https://www.doabooks.org"
        )
        return

    # Parse: bookdl_<chat_id>_<index>
    try:
        parts = data.split("_", 2)   # ["bookdl", chat_id, index]
        book_index = int(parts[2])
        stored_chat_id = parts[1]
    except (IndexError, ValueError):
        await query.message.reply_text("❌ خطای داخلی. لطفاً دوباره جستجو کنید.")
        return

    # Retrieve book dict from bot_data
    books: list = (context.bot_data.get("books") or {}).get(stored_chat_id, [])
    if book_index >= len(books):
        await query.message.reply_text("❌ اطلاعات کتاب منقضی شده. لطفاً دوباره جستجو کنید.")
        return

    book = books[book_index]
    if not book.get("download_url"):
        await query.message.reply_text("❌ لینک دانلود این کتاب موجود نیست.")
        return

    # Disable buttons to prevent double-tap
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    source_label = book.get("source_label", "کتابخانه دیجیتال")
    ext_tag = book.get("file_ext", ".epub").lstrip(".").upper()

    wait_msg = await query.message.reply_text(
        f"⏳ در حال دانلود کتاب از {source_label}...\n"
        f"📖 *{book['title']}*\n"
        f"📄 فرمت: {ext_tag}\n"
        "این ممکن است چند ثانیه طول بکشد.",
        parse_mode="Markdown",
    )

    # Download in a thread-safe temp directory
    with tempfile.TemporaryDirectory(prefix="book_dl_") as tmp_dir:
        try:
            file_path = await download_book(book, tmp_dir)
        except Exception:
            logger.exception("Book download exception: %s", book.get("title"))
            await context.bot.send_message(chat_id, "❌ خطا در دانلود کتاب. لطفاً دوباره تلاش کنید.")
            await log_upload_failed("book", chat_id)
            return
        finally:
            try:
                await wait_msg.delete()
            except Exception:
                pass

        if file_path is None:
            await context.bot.send_message(
                chat_id,
                f"❌ فایل این کتاب در دسترس نیست یا حجم آن بیش از ۱۸ مگابایت است.\n\n"
                f"📖 *{book['title']}*\n"
                f"می‌توانید آن را مستقیماً از {source_label} دانلود کنید.",
                parse_mode="Markdown",
            )
            await log_upload_failed("book", chat_id)
            return

        # Send the file
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        caption = (
            f"📖 *{book['title']}*\n"
            f"✍️ {book['author']}\n"
            f"📦 حجم: {file_size_mb:.1f} مگابایت\n"
            f"🌐 منبع: {source_label}"
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
            await log_upload_success("book", chat_id)
        except Exception:
            logger.exception("Failed to send book file: %s", file_path)
            await context.bot.send_message(chat_id, "❌ خطا در ارسال فایل. لطفاً دوباره تلاش کنید.")
            await log_upload_failed("book", chat_id)
