import os
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.book import get_dbooks_download_url, download_pdf

async def handle_book_state(update: Update, context: ContextTypes.DEFAULT_TYPE, step: str, text: str, chat_id: str, state_data: dict):
    
    if step == "waiting_book_selection":
        if text.startswith("📥 دانلود شماره "):
            try:
                index = int(text.replace("📥 دانلود شماره ", "").strip()) - 1
                books = state_data.get("books", [])
                selected_book = books[index]

                await update.message.reply_text(f"⏳ در حال دانلود PDF:\n**{selected_book['title']}**...")

                dl_link = selected_book["pdf_url"]
                if dl_link == "needs_fetch":
                    dl_link = await asyncio.to_thread(get_dbooks_download_url, selected_book["id"])

                file_path = await asyncio.to_thread(download_pdf, dl_link, selected_book["title"])

                if file_path and os.path.exists(file_path):
                    await update.message.reply_text("✅ در حال آپلود...")
                    try:
                        with open(file_path, "rb") as doc:
                            await context.bot.send_document(chat_id=chat_id, document=doc)
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    await update.message.reply_text("❌ خطا در دانلود فایل PDF.")
            except Exception as e:
                await update.message.reply_text("❌ انتخاب نامعتبر است یا خطایی رخ داد.")
