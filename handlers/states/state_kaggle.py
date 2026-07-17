# handlers/states/state_kaggle.py
"""
Kaggle download state handler + async worker queue.

Queue design:
  - 3 concurrent worker tasks (lazy-started on first use).
  - Each worker calls process_kaggle_download() which:
      1. Enforces daily quota (free=1, VIP=5).
      2. Downloads the dataset from Kaggle into a temp dir.
      3. Splits into ≤19 MB ZIP parts.
      4. Sends each part to the user via send_document().
      5. Increments the counter and logs the success.
      6. Cleans up temp directories.
"""

import asyncio
import logging
import os
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.state_manager import clear_state, set_state
from core.database import (
    get_kaggle_downloads,
    increment_kaggle_downloads,
    is_vip,
    log_upload_success,
    KAGGLE_LIMIT_FREE,
    KAGGLE_LIMIT_VIP,
)
from services.kaggle import (
    search_datasets,
    download_dataset,
    split_into_20mb_zips_async,
    format_dataset_size,
    dataset_ref,
    make_temp_dirs,
    cleanup_temp,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Async Worker Queue
# ──────────────────────────────────────────────────────────────────────────────
_kaggle_queue: asyncio.Queue = asyncio.Queue()
_workers_started: bool = False
_NUM_WORKERS = 3


async def _kaggle_worker():
    """Continuously processes Kaggle download tasks from the queue."""
    while True:
        func, args = await _kaggle_queue.get()
        try:
            await func(*args)
        except Exception:
            logger.exception("Kaggle worker error")
        finally:
            _kaggle_queue.task_done()


def _ensure_workers_started():
    """Lazily start worker tasks the first time a job is enqueued."""
    global _workers_started
    if not _workers_started:
        for _ in range(_NUM_WORKERS):
            asyncio.create_task(_kaggle_worker())
        _workers_started = True


async def _enqueue(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str, ref: str, user_id: str):
    """Add a download job to the queue and inform the user."""
    _ensure_workers_started()
    position = _kaggle_queue.qsize()
    if position > 0:
        await context.bot.send_message(
            chat_id,
            f"⏳ درخواست شما در صف قرار گرفت. (نفرات قبل از شما: {position})\n"
            f"لطفاً منتظر بمانید...",
        )
    else:
        await context.bot.send_message(chat_id, "⏳ شروع دانلود از کاگل...")

    await _kaggle_queue.put(
        (process_kaggle_download, (context, chat_id, ref, user_id))
    )


# ──────────────────────────────────────────────────────────────────────────────
# Core download processor
# ──────────────────────────────────────────────────────────────────────────────
async def process_kaggle_download(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    ref: str,
    user_id: str,
):
    """
    Full download pipeline:
      download → split into ≤19 MB ZIPs → send all parts → cleanup.
    """
    # ── Re-check quota (someone else may have used the slot while in queue) ──
    vip = await is_vip(user_id)
    limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
    used = await get_kaggle_downloads(user_id)
    if used >= limit:
        await context.bot.send_message(
            chat_id,
            "❌ محدودیت دانلود روزانه شما به اتمام رسیده است.\n"
            f"(رایگان: {KAGGLE_LIMIT_FREE}/روز | VIP: {KAGGLE_LIMIT_VIP}/روز)",
        )
        return

    await context.bot.send_message(chat_id, f"🔄 نوبت شما رسید! در حال دانلود «{ref}» از کاگل...")

    dl_dir, zip_dir = make_temp_dirs()
    safe_name = ref.replace("/", "_")

    try:
        # ── Step 1: Download & unzip ──
        try:
            await download_dataset(ref, dl_dir)
        except Exception as e:
            logger.exception("Kaggle download failed: %s", ref)
            await context.bot.send_message(
                chat_id,
                f"❌ خطا در دانلود دیتاست از کاگل.\n"
                f"مطمئن شوید نام دیتاست صحیح است: `{ref}`\n"
                f"جزئیات: {type(e).__name__}",
                parse_mode="Markdown",
            )
            return

        # ── Step 2: Check if anything was downloaded ──
        total_files = sum(len(files) for _, _, files in os.walk(dl_dir))
        if total_files == 0:
            await context.bot.send_message(
                chat_id,
                "❌ فایلی برای دانلود یافت نشد. ممکن است دیتاست خصوصی باشد یا آدرس اشتباه باشد.",
            )
            return

        await context.bot.send_message(
            chat_id,
            f"✅ دانلود کامل شد! در حال تقسیم‌بندی فایل‌ها (حداکثر ۱۹ مگابایت هر قسمت)..."
        )

        # ── Step 3: Split into ≤19 MB ZIPs ──
        parts = await split_into_20mb_zips_async(dl_dir, zip_dir, safe_name)
        if not parts:
            await context.bot.send_message(chat_id, "❌ خطا در آماده‌سازی فایل‌ها.")
            return

        total_parts = len(parts)
        await context.bot.send_message(
            chat_id,
            f"📦 دیتاست به {total_parts} قسمت تقسیم شد. در حال ارسال..."
        )

        # ── Step 4: Send each part ──
        sent_ok = True
        for i, part_path in enumerate(parts, 1):
            part_size_mb = os.path.getsize(part_path) / (1024 * 1024)
            caption = (
                f"📦 دیتاست: `{ref}`\n"
                f"قسمت {i} از {total_parts} | حجم: {part_size_mb:.1f} مگابایت"
            )
            try:
                with open(part_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=os.path.basename(part_path),
                        caption=caption,
                        parse_mode="Markdown",
                    )
            except Exception:
                logger.exception("Failed to send Kaggle part %s", part_path)
                await context.bot.send_message(
                    chat_id,
                    f"❌ خطا در ارسال قسمت {i}. لطفاً دوباره تلاش کنید.",
                )
                sent_ok = False
                break

        # ── Step 5: Increment counter & log (only if at least part 1 sent) ──
        if sent_ok or i > 1:
            await increment_kaggle_downloads(user_id)
            await log_upload_success("kaggle", user_id)

        if sent_ok:
            remaining = max(0, limit - used - 1)
            await context.bot.send_message(
                chat_id,
                f"✅ ارسال کامل شد!\n"
                f"⬇️ دانلودهای باقی‌مانده امروز: {remaining}",
            )

    finally:
        cleanup_temp(dl_dir)
        clear_state(chat_id)


# ──────────────────────────────────────────────────────────────────────────────
# State handler (called from states/__init__.py)
# ──────────────────────────────────────────────────────────────────────────────
async def handle_kaggle_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    user_id = str(update.effective_user.id)
    vip = await is_vip(user_id)
    limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
    used = await get_kaggle_downloads(user_id)

    if used >= limit:
        await update.message.reply_text(
            f"❌ محدودیت دانلود روزانه شما به اتمام رسیده است.\n"
            f"کاربر رایگان: {KAGGLE_LIMIT_FREE} دانلود در روز\n"
            f"کاربر VIP 🌟: {KAGGLE_LIMIT_VIP} دانلود در روز"
        )
        clear_state(chat_id)
        return

    if step == "waiting_kaggle_search":
        await update.message.reply_text(f"🔍 در حال جستجوی «{text}» در کاگل...")
        try:
            datasets = await search_datasets(text, max_results=8)
        except Exception:
            logger.exception("Kaggle search failed")
            await update.message.reply_text("❌ خطا در ارتباط با سرور کاگل.")
            clear_state(chat_id)
            return

        if not datasets:
            await update.message.reply_text("❌ دیتاستی برای این جستجو یافت نشد.")
            clear_state(chat_id)
            return

        msg_text = f"🔍 نتایج جستجوی «{text}»:\n\n"
        keyboard = []
        for i, ds in enumerate(datasets, 1):
            ref = dataset_ref(ds)
            size = format_dataset_size(ds)
            title = getattr(ds, "title", ref) or ref
            msg_text += f"{i}. `{ref}`\n   📦 {size}\n\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {title[:35]}",
                    callback_data=f"kgdl_{ref}",
                )
            ])

        await update.message.reply_text(msg_text, parse_mode="Markdown")
        await update.message.reply_text(
            "👇 برای دانلود روی دکمه کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        clear_state(chat_id)

    elif step == "waiting_kaggle_dl_link":
        # Parse URL or plain ref
        ref = _parse_kaggle_ref(text)
        if not ref:
            await update.message.reply_text(
                "❌ فرمت نامعتبر. مثال:\n"
                "• `https://www.kaggle.com/datasets/owner/name`\n"
                "• `owner/name`",
                parse_mode="Markdown",
            )
            return
        clear_state(chat_id)
        await _enqueue(update, context, chat_id, ref, user_id)


def _parse_kaggle_ref(text: str) -> str | None:
    """Parse a Kaggle URL or 'owner/dataset' string into a ref."""
    text = text.strip()
    # Match full URL: https://www.kaggle.com/datasets/owner/name
    url_match = re.search(
        r"kaggle\.com/datasets/([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)", text
    )
    if url_match:
        return url_match.group(1)
    # Match plain owner/dataset
    plain_match = re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+", text)
    if plain_match:
        return text
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Callback handler for inline ⬇️ download buttons (pattern: ^kgdl_)
# ──────────────────────────────────────────────────────────────────────────────
async def kaggle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks from search/popular result lists."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    chat_id = str(query.message.chat_id)
    ref = query.data.replace("kgdl_", "", 1)

    vip = await is_vip(user_id)
    limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
    used = await get_kaggle_downloads(user_id)

    if used >= limit:
        await query.message.reply_text(
            f"❌ محدودیت دانلود روزانه شما به اتمام رسیده است.\n"
            f"کاربر رایگان: {KAGGLE_LIMIT_FREE} دانلود در روز\n"
            f"کاربر VIP 🌟: {KAGGLE_LIMIT_VIP} دانلود در روز"
        )
        return

    # Disable the button to prevent double-tapping
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _enqueue(update, context, chat_id, ref, user_id)
