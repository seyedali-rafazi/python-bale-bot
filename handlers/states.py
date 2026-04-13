# handlers/states.py

import os
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from core.state_manager import get_state, set_state
from core.constants import *
from core.keyboards import get_yt_format_keyboard
from services.youtube import download_youtube_video, download_youtube_audio
from services.instagram import download_instagram
from services.book import get_dbooks_download_url, download_pdf
from services.ai import ask_chatbot, perform_ocr

async def process_state_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get('step')

    # بازگشت سریع به منو (جایگزین دکمه‌هایی که کیبورد را دور میزنند)
    if text in ['0', 'لغو', 'شروع']:
        from .commands import cmd_start
        await cmd_start(update, context)
        return

    if step == 'waiting_book_selection':
        if text.startswith("📥 دانلود شماره "):
            try:
                index = int(text.replace("📥 دانلود شماره ", "").strip()) - 1
                books = state_data.get('books', [])
                selected_book = books[index]
                
                await update.message.reply_text(f"⏳ در حال دانلود PDF:\n**{selected_book['title']}**...")
                
                dl_link = selected_book['pdf_url']
                if dl_link == 'needs_fetch':
                    dl_link = await asyncio.to_thread(get_dbooks_download_url, selected_book['id'])
                    
                file_path = await asyncio.to_thread(download_pdf, dl_link, selected_book['title'])
                
                if file_path and os.path.exists(file_path):
                    await update.message.reply_text("✅ در حال آپلود...")
                    try:
                        with open(file_path, 'rb') as doc:
                            await context.bot.send_document(chat_id=chat_id, document=doc)
                    finally:
                        if os.path.exists(file_path): os.remove(file_path) 
                else:
                    await update.message.reply_text("❌ خطا در دانلود فایل PDF.")
            except Exception as e:
                await update.message.reply_text("❌ انتخاب نامعتبر است یا خطایی رخ داد.")
        return

    elif step == 'waiting_yt_link':
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return
        set_state(chat_id, 'waiting_yt_format', yt_url=text)
        await update.message.reply_text("✅ لینک دریافت شد! فرمت را انتخاب کنید 👇", reply_markup=get_yt_format_keyboard())
        return

    elif step == 'waiting_yt_format':
        url = state_data.get('yt_url')
        if text == BTN_YT_VIDEO:
            await update.message.reply_text("⏳ در حال دانلود ویدیو...")
            file_path = await asyncio.to_thread(download_youtube_video, url)
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as vid:
                        await context.bot.send_video(chat_id=chat_id, video=vid)
                finally:
                    if os.path.exists(file_path): os.remove(file_path)
            else:
                await update.message.reply_text("❌ دانلود شکست خورد.")
            return

        elif text == BTN_YT_AUDIO:
            await update.message.reply_text("⏳ در حال استخراج صدا...")
            file_path, title, perf = await asyncio.to_thread(download_youtube_audio, url)
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as aud:
                        await context.bot.send_audio(chat_id=chat_id, audio=aud, title=title, performer=perf)
                finally:
                    if os.path.exists(file_path): os.remove(file_path)
            else:
                await update.message.reply_text("❌ دانلود شکست خورد.")
            return

    elif step == 'waiting_ig_link':
        if "instagram.com" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return
        await update.message.reply_text("⏳ در حال دانلود از اینستاگرام...")
        file_path = await asyncio.to_thread(download_instagram, text)
        if file_path and os.path.exists(file_path):
            try:
                if file_path.endswith('.mp4'):
                    with open(file_path, 'rb') as vid:
                        await context.bot.send_video(chat_id=chat_id, video=vid)
                else:
                    with open(file_path, 'rb') as doc:
                        await context.bot.send_document(chat_id=chat_id, document=doc)
            finally:
                if os.path.exists(file_path): os.remove(file_path)
        else:
            await update.message.reply_text("❌ دانلود شکست خورد.")
        return

    elif step == 'waiting_ai_chat':
        await update.message.reply_text("⏳ در حال فکر کردن...")
        answer = await asyncio.to_thread(ask_chatbot, text)
        await update.message.reply_text(answer)
        return
        
    if not step:
        await update.message.reply_text("لطفاً از منو استفاده کنید.")


async def process_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get('step') if state_data else None

    if step == 'waiting_ai_ocr':
        await update.message.reply_text("⏳ در حال دانلود و پردازش عکس...")
        
        try:
            # بررسی اینکه کاربر عکس را عادی فرستاده یا به صورت فایل (Document)
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
            elif update.message.document:
                file_id = update.message.document.file_id
            else:
                await update.message.reply_text("❌ فرمت فایل پشتیبانی نمی‌شود.")
                return

            # دانلود عکس از سرور تلگرام
            file = await context.bot.get_file(file_id)
            file_path = f"temp_ocr_{chat_id}.jpg"
            await file.download_to_drive(file_path)
            
            # پردازش OCR
            extracted_text = await asyncio.to_thread(perform_ocr, file_path)
            
            # حذف فایل موقت
            if os.path.exists(file_path):
                os.remove(file_path)
                
            await update.message.reply_text(f"✅ **متن استخراج شده:**\n\n{extracted_text}")
            
            # مهم: پاک کردن وضعیت کاربر تا ربات در حالت OCR گیر نکند
            set_state(chat_id, '')
            
        except Exception as e:
            await update.message.reply_text(f"❌ خطایی در پردازش عکس رخ داد: {e}")
            set_state(chat_id, '')
            
    else:
        await update.message.reply_text("متوجه نشدم. لطفاً از منو استفاده کنید.")

    chat_id = str(update.effective_chat.id)
    state_data = get_state(chat_id)
    step = state_data.get('step')

    if step == 'waiting_ai_ocr':
        # گرفتن عکسی که بالاترین کیفیت را دارد
        photo = update.message.photo[-1]
        
        await update.message.reply_text("⏳ در حال دانلود و پردازش عکس...")
        
        # دانلود عکس از سرور تلگرام/بله
        file = await context.bot.get_file(photo.file_id)
        file_path = f"temp_ocr_{chat_id}.jpg"
        await file.download_to_drive(file_path)
        
        # پردازش OCR
        extracted_text = await asyncio.to_thread(perform_ocr, file_path)
        
        # حذف فایل موقت
        if os.path.exists(file_path):
            os.remove(file_path)
            
        await update.message.reply_text(f"✅ **متن استخراج شده:**\n\n{extracted_text}")
    else:
        await update.message.reply_text("متوجه نشدم. لطفاً از منو استفاده کنید.")