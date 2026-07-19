# handlers/menus/research.py

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.database import get_kaggle_downloads, is_vip, KAGGLE_LIMIT_FREE, KAGGLE_LIMIT_VIP
from handlers.ensure_membership import ensure_membership
from services.kaggle import search_datasets, list_popular_datasets, format_dataset_size, dataset_ref

logger = logging.getLogger(__name__)


async def btn_research_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the research / مقاله و تحقیقات sub-menu."""
    if not await ensure_membership(update, context):
        return
    from core.keyboards import get_research_menu_keyboard

    await update.message.reply_text(
        "📚 *بخش مقاله و تحقیقات*\n\nاز این بخش می‌توانید دیتاست‌های علمی را جستجو و دانلود کنید:",
        reply_markup=get_research_menu_keyboard(),
        parse_mode="Markdown",
    )


async def btn_kaggle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the Kaggle sub-menu."""
    if not await ensure_membership(update, context):
        return
    from core.keyboards import get_kaggle_menu_keyboard

    user_id = str(update.effective_user.id)
    vip = await is_vip(user_id)
    limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
    used = await get_kaggle_downloads(user_id)
    remaining = max(0, limit - used)
    tier = "🌟 VIP" if vip else "رایگان"

    await update.message.reply_text(
        f"🗂 *کاگل — دانلود دیتاست*\n\n"
        f"📊 نوع حساب: {tier}\n"
        f"⬇️ دانلودهای باقی‌مانده امروز: {remaining} از {limit}\n\n"
        f"⚠️ دیتاست‌های بزرگ به قطعات ۱۹ مگابایتی تقسیم می‌شوند.",
        reply_markup=get_kaggle_menu_keyboard(),
        parse_mode="Markdown",
    )


async def btn_kaggle_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts user to enter a search term."""
    if not await ensure_membership(update, context):
        return
    set_state(str(update.effective_chat.id), "waiting_kaggle_search")
    await update.message.reply_text(
        "🔍 نام یا موضوع دیتاست را به انگلیسی وارد کنید:\n"
        "مثال: `titanic` یا `mnist` یا `covid`",
        parse_mode="Markdown",
    )


async def btn_kaggle_popular_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and shows popular datasets immediately."""
    if not await ensure_membership(update, context):
        return

    user_id = str(update.effective_user.id)
    vip = await is_vip(user_id)
    limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
    used = await get_kaggle_downloads(user_id)

    if used >= limit:
        await update.message.reply_text(
            f"❌ محدودیت دانلود روزانه شما به اتمام رسیده است.\n"
            f"کاربر رایگان: {KAGGLE_LIMIT_FREE} دانلود در روز\n"
            f"کاربر VIP: {KAGGLE_LIMIT_VIP} دانلود در روز"
        )
        return

    msg = await update.message.reply_text("⏳ در حال دریافت محبوب‌ترین دیتاست‌ها...")

    try:
        datasets = await list_popular_datasets(max_results=8)
        if not datasets:
            await msg.edit_text("❌ دیتاستی یافت نشد.")
            return

        text = "🔥 *محبوب‌ترین دیتاست‌های کاگل:*\n\n"
        keyboard = []
        for i, ds in enumerate(datasets, 1):
            ref = dataset_ref(ds)
            size = format_dataset_size(ds)
            title = getattr(ds, "title", ref) or ref
            text += f"{i}. `{ref}`\n   📦 {size}\n\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {title[:35]}",
                    callback_data=f"kgdl_{ref}",
                )
            ])

        await msg.edit_text(text, parse_mode="Markdown")
        await update.message.reply_text(
            "👇 برای دانلود روی دکمه کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.exception("Kaggle popular fetch failed")
        await msg.edit_text("❌ خطا در ارتباط با سرور کاگل. لطفاً دوباره تلاش کنید.")


async def btn_kaggle_dl_link_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts user to enter a Kaggle dataset URL."""
    if not await ensure_membership(update, context):
        return
    set_state(str(update.effective_chat.id), "waiting_kaggle_dl_link")
    await update.message.reply_text(
        "🔗 لینک دیتاست کاگل یا مسیر آن را وارد کنید:\n\n"
        "مثال:\n"
        "• `https://www.kaggle.com/datasets/heptapod/titanic`\n"
        "• `heptapod/titanic`",
        parse_mode="Markdown",
    )


async def btn_book_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the book download sub-menu."""
    if not await ensure_membership(update, context):
        return
    from core.keyboards import get_book_menu_keyboard

    await update.message.reply_text(
        "📖 *بخش دانلود کتاب*\n\n"
        "از این بخش می‌توانید کتاب‌های رایگان و عمومی را جستجو و دانلود کنید.\n\n"
        "📚 منبع: Open Library & Internet Archive\n"
        "📄 فرمت: PDF / EPUB",
        reply_markup=get_book_menu_keyboard(),
        parse_mode="Markdown",
    )


async def btn_book_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts user to enter a book title or author."""
    if not await ensure_membership(update, context):
        return
    set_state(str(update.effective_chat.id), "waiting_book_search")
    await update.message.reply_text(
        "🔍 نام کتاب یا نویسنده را وارد کنید:\n"
        "مثال: `Python Programming` یا `Clean Code` یا `ابوعلی سینا`",
        parse_mode="Markdown",
    )
