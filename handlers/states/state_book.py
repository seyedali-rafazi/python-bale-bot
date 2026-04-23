# handlers/states/state_book.py

import os
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import set_state, clear_state
from core.constants import BTN_BACK
from services.book import get_dbooks_download_url, download_pdf, search_books


async def handle_book_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    # --- مرحله اول: دریافت نام کتاب و جستجو ---
    if step == "waiting_book_search":
        query = text
        await update.message.reply_text(f"⏳ در حال جستجو برای `{query}`...")

        # جستجو در سرویس کتاب
        results = await asyncio.to_thread(search_books, query)

        if not results:
            await update.message.reply_text("❌ متأسفانه کتابی پیدا نشد.")
            clear_state(chat_id)  # خروج از وضعیت در صورت پیدا نشدن نتیجه
            return

        res_text = f"🔎 **نتایج برای:** {query}\n\n"
        download_buttons = []

        # ساخت لیست نتایج و دکمه‌های دانلود
        for i, book in enumerate(results, 1):
            res_text += f"{i}️⃣ **{book['title']}**\n👤 نویسنده: {book['author']}\n🌐 منبع: {book['source']}\n〰️〰️〰️\n"
            if book.get("has_pdf"):
                download_buttons.append(KeyboardButton(f"📥 دانلود شماره {i}"))

        # چیدمان دکمه‌ها (دو تا در هر ردیف)
        keyboard = [
            download_buttons[i : i + 2] for i in range(0, len(download_buttons), 2)
        ]
        keyboard.append([KeyboardButton(BTN_BACK)])

        # تغییر وضعیت به انتخاب کتاب و ذخیره نتایج در state_data
        set_state(chat_id, "waiting_book_selection", books=results)

        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    # --- مرحله دوم: انتخاب کتاب و دانلود ---
    elif step == "waiting_book_selection":
        if text.startswith("📥 دانلود شماره "):
            try:
                index = int(text.replace("📥 دانلود شماره ", "").strip()) - 1
                books = state_data.get("books", [])
                selected_book = books[index]

                await update.message.reply_text(
                    f"⏳ در حال دانلود PDF:\n**{selected_book['title']}**..."
                )

                dl_link = selected_book["pdf_url"]
                if dl_link == "needs_fetch":
                    dl_link = await asyncio.to_thread(
                        get_dbooks_download_url, selected_book["id"]
                    )

                file_path = await asyncio.to_thread(
                    download_pdf, dl_link, selected_book["title"]
                )

                if file_path and os.path.exists(file_path):
                    await update.message.reply_text("✅ در حال آپلود...")
                    try:
                        with open(file_path, "rb") as doc:
                            await context.bot.send_document(
                                chat_id=chat_id, document=doc
                            )
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    await update.message.reply_text("❌ خطا در دانلود فایل PDF.")
            except Exception as e:
                await update.message.reply_text(
                    "❌ انتخاب نامعتبر است یا خطایی رخ داد."
                )
