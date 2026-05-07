from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes
from handlers.commands import cmd_start
from core.state_manager import set_state, get_state
from core.constants import *
from core.keyboards import get_article_menu_keyboard, get_main_menu_article
from core.database import (
    is_vip,
    get_citation_count,
    get_user_usage_today,
    get_book_download_count,
    increment_book_download_count,
)
from services.book_service import download_book_pdf


async def btn_book_req(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "به بخش کتاب و مقاله خوش آمدید:", reply_markup=get_main_menu_article()
    )


async def btn_back_action(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await cmd_start(update, context)


async def btn_article_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 **به بخش جستجوی مقالات خوش آمدید!**\n\n"
        "💡 **راهنمای جستجو:**\n"
        "🔹 **جستجو با DOI:** ربات تلاش می‌کند مقاله را از پایگاه **Sci-Hub** دانلود کند (بهترین روش برای مقالات پولی و غیررایگان).\n"
        "🔹 **جستجو بر اساس نام:** ربات در پایگاه **OpenAlex** جستجو کرده و مقالاتی که نسخه رایگان (Open Access) دارند را برای شما پیدا می‌کند.\n\n"
        "یک گزینه را انتخاب کنید 👇"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=get_article_menu_keyboard()
    )


async def btn_search_doi_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_article_doi")

    text = (
        "🔍 **لطفاً شناسه DOI مقاله مورد نظر را بفرستید.**\n\n"
        "شما می‌توانید شناسه را به هر دو شکل زیر (لینک کامل یا فقط کد) ارسال کنید:\n\n"
        "🔸 **فقط کد:**\n"
        "`10.1364/oe.21.004958`\n"
        "🔸 **لینک کامل:**\n"
        "`https://doi.org/10.1364/oe.21.004958`"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_search_name_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_article_name")
    await update.message.reply_text(
        "🔎 لطفاً نام مقاله یا کلمات کلیدی آن را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# --- تابع جدید برای دکمه تولید رفرنس ---
async def btn_citation_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    # بررسی محدودیت استفاده (کاربر عادی حداکثر 3 بار)
    if not is_vip(chat_id) and get_citation_count(chat_id) >= 3:
        await update.message.reply_text(
            "❌ شما از تمام ظرفیت ($ 3 $ رفرنس) اکانت عادی خود استفاده کرده‌اید.\nبرای استفاده نامحدود، از طریق منوی اصلی حساب خود را VIP کنید."
        )
        return

    set_state(chat_id, "waiting_article_citation_doi")
    text = (
        "📑 **لطفاً شناسه DOI مقاله مورد نظر را جهت تولید رفرنس ارسال کنید:**\n\n"
        "💡 (می‌توانید هم لینک کامل و هم شناسه خالی را بفرستید)\n"
        "مثال‌ها:\n"
        "`10.1038/nature12373`\n"
        "`https://doi.org/10.1038/nature12373`"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


# --- تابع جدید برای دکمه چکیده هوشمند ---
async def btn_smart_abstract_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    # بررسی محدودیت استفاده
    user_is_vip = is_vip(chat_id)
    daily_limit = 20 if user_is_vip else 2
    usage_today = get_user_usage_today(chat_id, "smart_abstract")

    if usage_today >= daily_limit:
        await update.message.reply_text(
            f"❌ کاربر گرامی، شما به سقف مجاز روزانه خود ($ {daily_limit} $) رسیده‌اید و در حال حاضر قادر به ثبت درخواست جدید نیستید.\n\n"
            f"🌟 برای رفع این محدودیت و استفاده نامحدود از امکانات ربات، می‌توانید حساب کاربری خود را ارتقا دهید.\n\n"
            f"💎 با خرید اشتراک VIP از مزایای زیر بهره‌مند می‌شوید:\n"
            f"🔹 حذف محدودیت‌های روزانه\n"
            f"🔹 دسترسی به امکانات و قابلیت‌های ویژه\n"
            f"🔹 سرعت بالاتر و اولویت در پاسخ‌گویی\n\n"
            f"💳 برای خرید اشتراک VIP و ارتقای حساب، لطفاً از منوی مربوطه اقدام کنید."
        )

        return

    set_state(chat_id, "waiting_article_smart_abstract_doi")

    message_text = (
        "🧠 **به بخش چکیده هوشمند خوش آمدید!**\n\n"
        "در این بخش می‌توانید شناسه مقاله مورد نظر خود را ارسال کنید تا هوش مصنوعی چکیده آن را استخراج کرده و تحلیل جامعی از نکات کلیدی آن به شما ارائه دهد.\n\n"
        "✅ **فرمت‌های قابل پشتیبانی:**\n"
        "شما می‌توانید DOI را به هر دو شکل زیر ارسال کنید:\n"
        "🔗 **لینک کامل:**\n"
        "`https://doi.org/10.1364/oe.21.004958`\n"
        "🔢 **فقط شناسه:**\n"
        "`10.1364/oe.21.004958`\n\n"
        "👇 لطفاً DOI مقاله خود را ارسال کنید:"
    )

    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def btn_bibtex_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if not is_vip(chat_id):
        usage_today = get_user_usage_today(chat_id, "generate_bibtex")
        if usage_today >= 2:
            await update.message.reply_text(
                "❌ کاربر عادی عزیز، شما از تمام ظرفیت روزانه ($ }{2} $ بار) برای ابزار **تولید BibTeX** استفاده کرده‌اید.\nبرای استفاده نامحدود، اکانت خود را VIP کنید."
            )
            return

    set_state(chat_id, "waiting_article_bibtex_doi")
    await update.message.reply_text(
        "📜 **به بخش تولید فایل BibTeX خوش آمدید!**\n\n"
        "لطفاً شناسه DOI مقاله مورد نظر را ارسال کنید (مثال: `10.1038/nature12373`):",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
        parse_mode="Markdown",
    )


async def btn_book_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_article_book_name")
    await update.message.reply_text(
        "📕 لطفاً نام کتاب مورد نظر خود را (ترجیحاً به انگلیسی) ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(BTN_BACK)]], resize_keyboard=True
        ),
    )


async def inline_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat.id)
    data = query.data

    if data.startswith("dlbook_"):
        if not is_vip(chat_id) and get_book_download_count(chat_id) >= 4:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ شما از محدودیت دانلود کتاب (کلا $ 2 $ بار برای کاربر عادی) استفاده کرده‌اید. لطفا از منوی اصلی VIP تهیه کنید.",
            )
            return

        index = int(data.split("_")[1])
        state_data = get_state(chat_id)
        books = state_data.get("books", [])

        if index >= len(books):
            await context.bot.send_message(
                chat_id, "❌ خطای سیستمی. لطفا دوباره جستجو کنید."
            )
            return

        selected_book = books[index]

        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ در حال آماده‌سازی و آپلود فایل PDF. لطفاً صبور باشید...",
        )

        # دریافت فایل PDF از سرویس دانلود
        pdf_file = await download_book_pdf(selected_book)

        if pdf_file:
            # ثبت یک بار دانلود در دیتابیس
            increment_book_download_count(chat_id)

            caption = f"📕 **عنوان:** {selected_book['title']}\n👤 **نویسنده:** {selected_book['author']}"

            # آپلود فایل برای کاربر
            await context.bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                caption=caption,
                parse_mode="Markdown",
            )
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ متاسفانه در دانلود این کتاب مشکلی پیش آمد.")
