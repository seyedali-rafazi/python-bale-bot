# handlers/states/state_book.py

import os
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

    if step == "waiting_book_search":
        query = text
        await update.message.reply_text(f"⏳ در حال جستجو برای `{query}`...")

        # دیگر نیازی به to_thread نیست، توابع به صورت Async تعریف شده‌اند
        results = await search_books(query)

        if not results:
            await update.message.reply_text("❌ متأسفانه کتابی پیدا نشد.")
            clear_state(chat_id)
            return

        res_text = f"🔎 **نتایج برای:** {query}\n\n"
        download_buttons = []

        for i, book in enumerate(results, 1):
            res_text += f"{i}️⃣ **{book['title']}**\n👤 نویسنده: {book['author']}\n🌐 منبع: {book['source']}\n〰️〰️〰️\n"
            if book.get("has_pdf"):
                download_buttons.append(KeyboardButton(f"📥 دانلود شماره {i}"))

        keyboard = [
            download_buttons[i : i + 2] for i in range(0, len(download_buttons), 2)
        ]
        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_book_selection", books=results)

        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

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
                    dl_link = await get_dbooks_download_url(selected_book["id"])

                # ارسال فقط لینک دانلود به تابع (نام‌گذاری با UUID انجام می‌شود)
                file_path = await download_pdf(dl_link)

                if file_path and os.path.exists(file_path):
                    await update.message.reply_text("✅ در حال آپلود...")
                    try:
                        # تلگرام پایتون مسیر فایل را مستقیم می‌گیرد و به صورت Async آپلود می‌کند (نیاز به open نیست)
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=file_path,
                            filename=f"{selected_book['title']}.pdf",  # نام اصلی را اینجا به کاربر نمایش می‌دهیم
                        )
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    await update.message.reply_text("❌ خطا در دانلود فایل PDF.")
            except Exception as e:
                print(e)
                await update.message.reply_text(
                    "❌ انتخاب نامعتبر است یا خطایی رخ داد."
                )
