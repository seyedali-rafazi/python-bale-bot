# handlers/menus/books.py

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.constants import *
from core.keyboards import get_article_menu_keyboard, get_main_menu_article
from core.state_manager import get_state, set_state
from handlers.commands import cmd_start
from services.book.queue_manager import download_queue


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
        try:
            index = int(data.split("_")[1])
            state_data = get_state(chat_id)
            books = state_data.get("books", [])

            if not (0 <= index < len(books)):
                await context.bot.send_message(
                    chat_id, "❌ خطای سیستمی. لطفا دوباره جستجو کنید."
                )
                return

            selected_book = books[index]
            status_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ درخواست دانلود کتاب '{selected_book['title']}' به صف اضافه شد. به محض آماده شدن، فایل برای شما ارسال خواهد شد.",
            )

            job = {
                "chat_id": chat_id,
                "book_data": selected_book,
                "status_msg_id": status_msg.message_id,
            }
            await download_queue.put(job)
        except (ValueError, IndexError):
            await context.bot.send_message(chat_id, "❌ درخواست نامعتبر است.")
        except Exception as e:
            print(f"Error in inline_buttons_handler: {e}")
            await context.bot.send_message(
                chat_id, "❌ خطایی در ثبت درخواست شما رخ داد."
            )
