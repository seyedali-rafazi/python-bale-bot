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
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.state_manager import StateCache, clear_state, set_state
from core.task_utils import bounded_large_upload, get_file_size_async, load_input_file
from handlers.utils import escape_markdown, safe_answer_query
from services.rate_limiter import user_action_lock
from core.database import (
    get_kaggle_downloads,
    increment_kaggle_downloads,
    is_vip,
    log_upload_failed,
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
_KAGGLE_QUEUE_MAXSIZE = max(10, int(os.getenv("KAGGLE_QUEUE_MAXSIZE", "100")))
_kaggle_queue: asyncio.Queue = asyncio.Queue(maxsize=_KAGGLE_QUEUE_MAXSIZE)
_worker_tasks: list[asyncio.Task] = []
_NUM_WORKERS = 3
_kaggle_ref_cache = StateCache(max_capacity=2000, default_ttl=3600.0)
_pending_kaggle_downloads: dict[str, int] = {}


def kaggle_callback_data(ref: str) -> str:
    direct = f"kgdl_{ref}"
    if len(direct.encode("utf-8")) <= 64:
        return direct
    token = uuid.uuid4().hex[:12]
    _kaggle_ref_cache[token] = ref
    return f"kgdl_tok_{token}"


async def _kaggle_worker():
    """Continuously processes Kaggle download tasks from the queue."""
    while True:
        func, args = await _kaggle_queue.get()
        try:
            await func(*args)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Kaggle worker error")
        finally:
            _kaggle_queue.task_done()


def _ensure_workers_started():
    """Lazily start worker tasks and replace any exited workers."""
    _worker_tasks[:] = [t for t in _worker_tasks if not t.done()]
    while len(_worker_tasks) < _NUM_WORKERS:
        _worker_tasks.append(asyncio.create_task(_kaggle_worker()))


async def stop_kaggle_workers() -> None:
    for task in _worker_tasks:
        if not task.done():
            task.cancel()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()


async def _enqueue(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str, ref: str, user_id: str):
    """Add a download job to the queue and inform the user."""
    _ensure_workers_started()
    if _kaggle_queue.full():
        await context.bot.send_message(
            chat_id,
            "🔴 صف دانلود کاگل در حال حاضر پر است. لطفاً چند لحظه دیگر تلاش کنید.",
        )
        return

    position = _kaggle_queue.qsize()
    if position > 0:
        await context.bot.send_message(
            chat_id,
            f"⏳ درخواست شما در صف قرار گرفت. (نفرات قبل از شما: {position})\n"
            f"لطفاً منتظر بمانید...",
        )
    else:
        await context.bot.send_message(chat_id, "⏳ شروع دانلود از کاگل...")

    try:
        _kaggle_queue.put_nowait(
            (process_kaggle_download, (context, chat_id, ref, user_id))
        )
    except asyncio.QueueFull:
        await context.bot.send_message(
            chat_id,
            "🔴 صف دانلود کاگل در حال حاضر پر است. لطفاً چند لحظه دیگر تلاش کنید.",
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
    vip, used = await asyncio.gather(is_vip(user_id), get_kaggle_downloads(user_id))
    limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
    if used >= limit:
        await context.bot.send_message(
            chat_id,
            "❌ محدودیت دانلود روزانه شما به اتمام رسیده است.\n"
            f"(رایگان: {KAGGLE_LIMIT_FREE}/روز | VIP: {KAGGLE_LIMIT_VIP}/روز)",
        )
        return

    status_msg = await context.bot.send_message(
        chat_id, f"🔄 نوبت شما رسید! در حال دانلود «{ref}» از کاگل..."
    )

    dl_dir, zip_dir = await asyncio.to_thread(make_temp_dirs)
    safe_name = ref.replace("/", "_")

    try:
        # ── Step 1: Download & unzip ──
        try:
            await download_dataset(ref, dl_dir)
        except Exception as e:
            logger.exception("Kaggle download failed: %s", ref)
            await status_msg.edit_text(
                f"❌ خطا در دانلود دیتاست از کاگل.\n"
                f"مطمئن شوید نام دیتاست صحیح است: `{ref}`\n"
                f"جزئیات: {type(e).__name__}",
                parse_mode="Markdown",
            )
            await log_upload_failed("kaggle", user_id)
            return

        # ── Step 2: Check if anything was downloaded ──
        total_files = await asyncio.to_thread(
            lambda: sum(len(files) for _, _, files in os.walk(dl_dir))
        )
        if total_files == 0:
            await status_msg.edit_text(
                "❌ فایلی برای دانلود یافت نشد. ممکن است دیتاست خصوصی باشد یا آدرس اشتباه باشد.",
            )
            return

        await status_msg.edit_text(
            "✅ دانلود کامل شد! در حال تقسیم‌بندی فایل‌ها (حداکثر ۱۹ مگابایت هر قسمت)..."
        )

        # ── Step 3: Split into ≤19 MB ZIPs ──
        parts = await split_into_20mb_zips_async(dl_dir, zip_dir, safe_name)
        if not parts:
            await status_msg.edit_text("❌ خطا در آماده‌سازی فایل‌ها.")
            return

        total_parts = len(parts)
        await status_msg.edit_text(
            f"📦 دیتاست به {total_parts} قسمت تقسیم شد. در حال ارسال..."
        )

        # ── Step 4: Send each part ──
        sent_ok = True
        for i, part_path in enumerate(parts, 1):
            part_size_mb = (await get_file_size_async(part_path)) / (1024 * 1024)
            caption = (
                f"📦 دیتاست: `{escape_markdown(ref)}`\n"
                f"قسمت {i} از {total_parts} | حجم: {part_size_mb:.1f} مگابایت"
            )
            try:
                async with bounded_large_upload():
                    doc_file = await load_input_file(part_path, filename=os.path.basename(part_path))
                    try:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=doc_file,
                            filename=os.path.basename(part_path),
                            caption=caption,
                            parse_mode="Markdown",
                        )
                    finally:
                        del doc_file
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

        if sent_ok:
            remaining = max(0, limit - used - 1)
            await context.bot.send_message(
                chat_id,
                f"✅ ارسال کامل شد!\n"
                f"⬇️ دانلودهای باقی‌مانده امروز: {remaining}",
            )
        else:
            await log_upload_failed("kaggle", user_id)

    finally:
        await asyncio.to_thread(cleanup_temp, dl_dir)
        uid = str(user_id)
        cur = _pending_kaggle_downloads.get(uid, 0)
        if cur <= 1:
            _pending_kaggle_downloads.pop(uid, None)
        else:
            _pending_kaggle_downloads[uid] = cur - 1


async def start_kaggle_dataset_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    chat_id: str,
    *,
    keep_state: bool = True,
) -> None:
    user_id = str(update.effective_user.id)
    ref = _parse_kaggle_ref(text)
    if not ref:
        await update.message.reply_text(
            "❌ فرمت نامعتبر. مثال:\n"
            "• `https://www.kaggle.com/datasets/owner/name`\n"
            "• `owner/name`",
            parse_mode="Markdown",
        )
        return

    async with user_action_lock(user_id, "kaggle_dl", timeout_sec=10) as acquired:
        if not acquired:
            await update.message.reply_text("⏳ درخواست قبلی شما در حال ثبت است. لطفاً صبر کنید.")
            return
        vip, used = await asyncio.gather(
            is_vip(user_id),
            get_kaggle_downloads(user_id),
        )
        limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
        pending = _pending_kaggle_downloads.get(user_id, 0)

        if used + pending >= limit:
            await update.message.reply_text(
                f"❌ محدودیت دانلود روزانه شما به اتمام رسیده است.\n"
                f"کاربر رایگان: {KAGGLE_LIMIT_FREE} دانلود در روز\n"
                f"کاربر VIP 🌟: {KAGGLE_LIMIT_VIP} دانلود در روز"
            )
            return

        _pending_kaggle_downloads[user_id] = pending + 1
        if keep_state:
            set_state(chat_id, "waiting_kaggle_dl_link")
        try:
            await _enqueue(update, context, chat_id, ref, user_id)
        except BaseException:
            cur = _pending_kaggle_downloads.get(user_id, 0)
            if cur <= 1:
                _pending_kaggle_downloads.pop(user_id, None)
            else:
                _pending_kaggle_downloads[user_id] = cur - 1
            raise


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

    if step == "waiting_kaggle_search":
        await update.message.reply_text(f"🔍 در حال جستجوی «{text}» در کاگل...")
        try:
            datasets = await search_datasets(text, max_results=8)
        except Exception:
            logger.exception("Kaggle search failed")
            await update.message.reply_text("❌ خطا در ارتباط با سرور کاگل.")
            await log_upload_failed("kaggle", user_id)
            clear_state(chat_id)
            return

        if not datasets:
            await update.message.reply_text("❌ دیتاستی برای این جستجو یافت نشد.")
            clear_state(chat_id)
            return

        msg_text = f"🔍 نتایج جستجوی «{escape_markdown(text)}»:\n\n"
        keyboard = []
        for i, ds in enumerate(datasets, 1):
            ref = dataset_ref(ds)
            size = format_dataset_size(ds)
            title = getattr(ds, "title", ref) or ref
            msg_text += f"{i}. `{escape_markdown(ref)}`\n   📦 {size}\n\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {title[:35]}",
                    callback_data=kaggle_callback_data(ref),
                )
            ])

        await update.message.reply_text(
            msg_text + "👇 برای دانلود روی دکمه کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        clear_state(chat_id)

    elif step == "waiting_kaggle_dl_link":
        await start_kaggle_dataset_download(update, context, text, chat_id, keep_state=True)


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
    await safe_answer_query(query)

    user_id = str(query.from_user.id)
    chat_id = str(query.message.chat_id)
    raw_ref = (query.data or "").replace("kgdl_", "", 1)
    if raw_ref.startswith("tok_"):
        ref = _kaggle_ref_cache.get(raw_ref[4:])
        if not ref:
            await query.message.reply_text("❌ نشست منقضی شده است. لطفاً دوباره جستجو کنید.")
            return
    else:
        ref = raw_ref

    async with user_action_lock(user_id, "kaggle_dl", timeout_sec=10) as acquired:
        if not acquired:
            await query.message.reply_text("⏳ درخواست قبلی شما در حال ثبت است. لطفاً صبر کنید.")
            return

        vip, used = await asyncio.gather(
            is_vip(user_id),
            get_kaggle_downloads(user_id),
        )
        limit = KAGGLE_LIMIT_VIP if vip else KAGGLE_LIMIT_FREE
        pending = _pending_kaggle_downloads.get(user_id, 0)

        if used + pending >= limit:
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

        _pending_kaggle_downloads[user_id] = pending + 1
        try:
            await _enqueue(update, context, chat_id, ref, user_id)
        except BaseException:
            cur = _pending_kaggle_downloads.get(user_id, 0)
            if cur <= 1:
                _pending_kaggle_downloads.pop(user_id, None)
            else:
                _pending_kaggle_downloads[user_id] = cur - 1
            raise
