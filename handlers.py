# handlers.py

import os
import asyncio
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes

from state_manager import get_state, set_state, clear_state
from downloader import download_youtube_video, download_youtube_audio, download_instagram
from translator import translate_text 
from weather import get_weather_forecast 
from book import search_books, get_dbooks_download_url, download_pdf 

# ==========================================
# تعریف متن دکمه‌ها (ثابت‌ها)
# ==========================================
BTN_DL_YOUTUBE = "📺 دانلود از یوتیوب"
BTN_DL_INSTA = "📸 دانلود از اینستاگرام"
BTN_TRANSLATE = "🔤 ترجمه متن"
BTN_WEATHER = "🌤 آب و هوا"
BTN_BOOK = "📚 دانلود کتاب" 
BTN_YT_VIDEO = "🎥 دانلود ویدیو (تصویری)"
BTN_YT_AUDIO = "🎵 دانلود فایل صوتی (MP3)"
BTN_BACK = "🔙 بازگشت به منو"

# ==========================================
# توابع ساخت کیبورد (پایین صفحه)
# ==========================================
def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton(BTN_DL_YOUTUBE)],
        [KeyboardButton(BTN_DL_INSTA)],
        [KeyboardButton(BTN_TRANSLATE), KeyboardButton(BTN_WEATHER)],
        [KeyboardButton(BTN_BOOK)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_yt_format_keyboard():
    keyboard = [
        [KeyboardButton(BTN_YT_VIDEO)],
        [KeyboardButton(BTN_YT_AUDIO)],
        [KeyboardButton(BTN_BACK)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def send_main_menu(update: Update, text="👋 به ربات خوش آمدید!\n\nلطفاً از کیبورد پایین یک گزینه را انتخاب کنید 👇"):
    chat_id = str(update.effective_chat.id)
    clear_state(chat_id)
    await update.message.reply_text(
        text=text,
        reply_markup=get_main_menu_keyboard()
    )

# ==========================================
# پردازشگر دستورات (Commands)
# ==========================================
async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    
    if text == '/start':
        await send_main_menu(update)
        return

    # --- دستور جستجوی کتاب ---
    if text.lower().startswith('/book '):
        query = text.split(maxsplit=1)[1]
        await update.message.reply_text(f"⏳ در حال جستجو برای کتاب `{query}` در منابع آزاد...\n(این کار ممکن است چند ثانیه طول بکشد)")
        
        results = await asyncio.to_thread(search_books, query)
        
        if not results:
            await update.message.reply_text("❌ متأسفانه کتابی با این عنوان پیدا نشد.")
            return
            
        res_text = f"🔎 **نتایج جستجو برای:** {query}\n\n"
        
        download_buttons = []
        for i, book in enumerate(results, 1):
            pdf_status = "✅ دارد" if book['has_pdf'] else "❌ ندارد"
            res_text += f"{i}️⃣ **{book['title']}**\n"
            res_text += f"👤 نویسنده: {book['author']}\n"
            res_text += f"🌐 منبع: {book['source']} | فایل PDF: {pdf_status}\n"
            res_text += "〰️〰️〰️〰️〰️〰️\n"
            if book['has_pdf']:
                download_buttons.append(KeyboardButton(f"📥 دانلود شماره {i}"))
            
        res_text += "\n👇 **لطفاً برای دانلود، از دکمه‌های پایین استفاده کنید:**"
        
        keyboard = []
        for i in range(0, len(download_buttons), 2):
            keyboard.append(download_buttons[i:i+2])
        keyboard.append([KeyboardButton(BTN_BACK)])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        set_state(chat_id, 'waiting_book_selection', books=results)
        await update.message.reply_text(res_text, reply_markup=reply_markup)
        return

    # --- دستور ترجمه ---
    if text.startswith('/tr '):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("❌ فرمت اشتباه است.\nمثال: `/tr fa:en سلام چطوری؟`")
            return
        lang_config, text_to_translate = parts[1], parts[2]
        if ':' not in lang_config:
            await update.message.reply_text("❌ فرمت زبان‌ها اشتباه است.")
            return
        source_lang, target_lang = lang_config.split(':', 1)
        await update.message.reply_text(f"⏳ در حال ترجمه از {source_lang} به {target_lang}...")
        result = await asyncio.to_thread(translate_text, source_lang, target_lang, text_to_translate)
        await update.message.reply_text(f"✅ **نتیجه ترجمه:**\n\n{result}")
        return

    # --- دستور آب و هوا ---
    if text.lower().startswith('/weather '):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("❌ نام شهر وارد نشده است.")
            return
        city_name = parts[1]
        await update.message.reply_text(f"⏳ در حال دریافت پیش‌بینی آب و هوای {city_name}...")
        result = await asyncio.to_thread(get_weather_forecast, city_name)
        await update.message.reply_text(result)
        return

# ==========================================
# پردازشگر متون و دکمه‌ها (Messages)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    print(f"💬 [پیام دریافت شد]: {text}")

    state_data = get_state(chat_id)
    step = state_data.get('step')

    # دستورات بازگشت و لغو
    if text in ['0', 'لغو', 'شروع', BTN_BACK]:
        await send_main_menu(update, "منوی اصلی:")
        return

    # --- کلیک روی دکمه‌های منوی اصلی ---
    
    if text == BTN_BOOK:
        help_text = (
            "📚 **راهنمای جستجو و دانلود کتاب:**\n\n"
            "برای پیدا کردن کتاب، دستور زیر را به همراه نام کتاب (به انگلیسی) بفرستید:\n\n"
            "`/book [نام کتاب]`\n\n"
            "🔹 **مثال:**\n"
            "`/book the startup`\n"
            "`/book python programming`"
        )
        await update.message.reply_text(help_text, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))
        return

    elif text == BTN_TRANSLATE:
        help_text = (
            "🔤 **راهنمای استفاده از مترجم:**\n\n"
            "برای ترجمه، کافیست از دستور `/tr` استفاده کنید.\n\n"
            "🔹 **فرمت:**\n"
            "`/tr [زبان مبدا]:[زبان مقصد] [متن شما]`\n\n"
            "🔹 **مثال (فارسی به انگلیسی):**\n"
            "`/tr fa:en سلام، روز بخیر`\n\n"
            "🔹 **مثال (انگلیسی به فارسی):**\n"
            "`/tr en:fa Hello, how are you?`"
        )
        await update.message.reply_text(help_text, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))
        return

    elif text == BTN_WEATHER:
        help_text = (
            "🌤 **راهنمای دریافت آب و هوا:**\n\n"
            "برای مشاهده وضعیت آب و هوای هر شهر، از دستور `/weather` استفاده کنید.\n\n"
            "🔹 **مثال‌ها:**\n"
            "`/weather Tehran`\n"
            "`/weather Shiraz`\n"
            "`/weather London`"
        )
        await update.message.reply_text(help_text, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True))
        return

    elif text == BTN_DL_YOUTUBE:
        set_state(chat_id, 'waiting_yt_link')
        await update.message.reply_text(
            "🔗 لطفاً لینک ویدیو یوتیوب را ارسال کنید:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
        )
        return

    elif text == BTN_DL_INSTA:
        set_state(chat_id, 'waiting_ig_link')
        await update.message.reply_text(
            "📸 لطفاً لینک پست یا ریلز اینستاگرام را ارسال کنید:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True)
        )
        return

    # --- ماشین وضعیت (State Machine) ---

    if step == 'waiting_book_selection':
        if text.startswith("📥 دانلود شماره "):
            try:
                num_str = text.replace("📥 دانلود شماره ", "").strip()
                index = int(num_str) - 1
                
                books = state_data.get('books', [])
                
                if index < 0 or index >= len(books):
                    await update.message.reply_text("❌ خطایی رخ داد. این شماره در لیست نیست.")
                    return
                    
                selected_book = books[index]
                await update.message.reply_text(f"⏳ در حال آماده‌سازی و دانلود فایل PDF برای کتاب:\n**{selected_book['title']}**...")
                
                download_link = selected_book['pdf_url']
                if download_link == 'needs_fetch':
                    download_link = await asyncio.to_thread(get_dbooks_download_url, selected_book['id'])
                    
                if not download_link:
                    await update.message.reply_text("❌ خطا در دریافت لینک دانلود از سرور منبع.")
                    return
                    
                file_path = await asyncio.to_thread(download_pdf, download_link, selected_book['title'])
                
                if file_path and os.path.exists(file_path):
                    await update.message.reply_text("✅ فایل دریافت شد. در حال آپلود در چت...")
                    try:
                        with open(file_path, 'rb') as doc:
                            await context.bot.send_document(chat_id=chat_id, document=doc)
                    except Exception as e:
                        print(f"Book Upload error: {e}")
                        await update.message.reply_text("❌ متأسفانه حجم فایل بسیار بالاست یا در آپلود خطایی رخ داد.")
                    finally:
                        if os.path.exists(file_path): os.remove(file_path) 
                        
                    await send_main_menu(update, "📚 دانلود انجام شد. گزینه بعدی؟")
                else:
                    await update.message.reply_text("❌ خطا در دانلود فایل PDF از سرور منبع.")
                    
            except ValueError:
                await update.message.reply_text("❌ انتخاب نامعتبر است.")
        else:
            await update.message.reply_text("❌ لطفاً برای دانلود، از دکمه‌های کیبورد پایین استفاده کنید.")
        return

    elif step == 'waiting_yt_link':
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است. لطفاً یک لینک صحیح از یوتیوب بفرستید.")
            return
            
        set_state(chat_id, 'waiting_yt_format', yt_url=text)
        await update.message.reply_text(
            "✅ لینک دریافت شد! لطفاً فرمت دانلود را از منوی پایین انتخاب کنید 👇",
            reply_markup=get_yt_format_keyboard()
        )
        return

    elif step == 'waiting_yt_format':
        url = state_data.get('yt_url')
        if not url:
            await send_main_menu(update, "❌ خطایی رخ داده است. لطفاً دوباره تلاش کنید.")
            return

        if text == BTN_YT_VIDEO:
            await update.message.reply_text("⏳ در حال دانلود ویدیو... لطفاً صبور باشید.")
            file_path = await asyncio.to_thread(download_youtube_video, url)
            
            if file_path and os.path.exists(file_path):
                await update.message.reply_text("✅ دانلود تمام شد! در حال ارسال...")
                try:
                    with open(file_path, 'rb') as vid:
                        await context.bot.send_video(chat_id=chat_id, video=vid)
                except Exception as e:
                    print(f"Upload error: {e}")
                    await update.message.reply_text("❌ متاسفانه در ارسال ویدیو خطایی رخ داد (احتمالا حجم فایل بیش از حد مجاز است).")
                finally:
                    if os.path.exists(file_path): os.remove(file_path)
            else:
                await update.message.reply_text("❌ دانلود با شکست مواجه شد. لطفاً بررسی کنید ویدیو در دسترس باشد.")
                
            await send_main_menu(update)
            return

        elif text == BTN_YT_AUDIO:
            await update.message.reply_text("⏳ در حال دانلود و تبدیل به فایل صوتی... لطفاً صبور باشید.")
            file_path, title, performer = await asyncio.to_thread(download_youtube_audio, url)
            
            if file_path and os.path.exists(file_path):
                await update.message.reply_text("✅ دانلود تمام شد! در حال ارسال...")
                try:
                    with open(file_path, 'rb') as aud:
                        await context.bot.send_audio(chat_id=chat_id, audio=aud, title=title, performer=performer)
                except Exception as e:
                    print(f"Upload error: {e}")
                    await update.message.reply_text("❌ متاسفانه در ارسال فایل صوتی خطایی رخ داد.")
                finally:
                    if os.path.exists(file_path): os.remove(file_path)
            else:
                await update.message.reply_text("❌ استخراج فایل صوتی با شکست مواجه شد.")
                
            await send_main_menu(update)
            return
            
        else:
            await update.message.reply_text("❌ لطفاً یک گزینه معتبر از کیبورد پایین انتخاب کنید.")
            return

    elif step == 'waiting_ig_link':
        if "instagram.com" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است. لطفاً یک لینک صحیح از اینستاگرام بفرستید.")
            return
            
        await update.message.reply_text("⏳ در حال پردازش و دانلود از اینستاگرام... این کار ممکن است کمی طول بکشد.")
        file_path = await asyncio.to_thread(download_instagram, text)
        
        if file_path and os.path.exists(file_path):
            await update.message.reply_text("✅ فایل دریافت شد! در حال ارسال...")
            try:
                if file_path.endswith('.mp4'):
                    with open(file_path, 'rb') as vid:
                        await context.bot.send_video(chat_id=chat_id, video=vid)
                else:
                    with open(file_path, 'rb') as doc:
                        await context.bot.send_document(chat_id=chat_id, document=doc)
            except Exception as e:
                print(f"Upload error: {e}")
                await update.message.reply_text("❌ متاسفانه در ارسال فایل خطایی رخ داد.")
            finally:
                if os.path.exists(file_path): os.remove(file_path)
        else:
            await update.message.reply_text("❌ دانلود با شکست مواجه شد. ممکن است پیج پرایوت باشد یا ساختار لینک تغییر کرده باشد.")
            
        await send_main_menu(update)
        return

    if not step:
        await update.message.reply_text("لطفاً از دکمه‌های منو استفاده کنید یا از طریق /start منو را دوباره فرابخوانید.")
