# handlers/states/state_software.py
"""
Software download state handler and callback query processor.
High-concurrency optimized:
  - Semaphore-controlled worker queue for heavy downloads to prevent server starvation.
  - Offloading CPU-bound ZIP compression/splitting to worker threads (asyncio.to_thread)
    so the asyncio event loop NEVER blocks.
  - Generous I/O timeouts for Bale upload reliability.
  - Instant button disabling on click to prevent duplicate download requests.
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.database.monitoring import log_upload_failed, log_upload_success
from core.state_manager import StateCache, async_clear_state, async_get_state, async_set_state, clear_state, set_state
from core.task_utils import async_temp_dir, get_file_size_async, load_input_file, track_task
from services.rate_limiter import user_action_lock
from services.software_service import (
    MAX_ALLOWED_DOWNLOAD_BYTES,
    SoftwareService,
    sanitize_filename,
)
from services.zip_utils import build_zip_and_split, format_merge_instructions

logger = logging.getLogger(__name__)

MAX_BALE_BYTES = 45 * 1024 * 1024   # 45 MB — حد split (ورودی به zip_utils)
MAX_BALE_SEND_BYTES = 40 * 1024 * 1024  # 40 MB — حد واقعی ارسال مستقیم (margin بیشتر)
MAX_ALLOWED_MB = MAX_ALLOWED_DOWNLOAD_BYTES // (1024 * 1024)  # 250 MB

# Concurrency semaphore: max 3 parallel downloads to prevent saturating bandwidth/CPU
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
_software_cache = StateCache(max_capacity=2000, default_ttl=3600.0)


async def handle_software_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: Dict[str, Any],
):
    """Called from states/__init__.py when user enters software query."""
    if step == "waiting_software_choice":
        await update.message.reply_text(
            "👇 لطفاً یکی از نرم‌افزارهای لیست بالا را انتخاب کنید یا دکمه «❌ لغو / جستجوی جدید» را بزنید."
        )
        return

    query = text.strip()
    if not query:
        await update.message.reply_text("❌ لطفاً نام برنامه مورد نظر خود را وارد کنید.")
        return

    is_android = step == "waiting_software_android"
    platform_key = "android" if is_android else "windows"
    platform_label = "اندروید" if is_android else "ویندوز"

    status_msg = await update.message.reply_text("🔍 در حال جستجو...")

    try:
        if is_android:
            results = await SoftwareService.search_android(query, limit=5)
        else:
            results = await SoftwareService.search_windows(query, limit=5)
    except Exception as e:
        logger.exception("Error searching %s software for '%s': %s", platform_key, query, e)
        await status_msg.edit_text("❌ خطا در جستجو. لطفاً مجدداً تلاش کنید.")
        await log_upload_failed("software", chat_id)
        return

    if not results:
        await status_msg.edit_text(
            f"❌ متأسفانه نرم‌افزاری برای «{query}» در مخزن {platform_label} یافت نشد.\n\n"
            "💡 راهنما:\n"
            "• نام انگلیسی برنامه را امتحان کنید (مثال: `telegram` یا `vlc`)\n"
            "• املای نام را بررسی نمایید."
        )
        return

    # Cache results in bounded TTL/LRU cache and user_states
    _software_cache[str(chat_id)] = results

    set_state(
        chat_id,
        "waiting_software_choice",
        software_results=results,
        software_platform=platform_key,
        software_query=query,
    )

    # Build inline keyboard
    keyboard: List[List[InlineKeyboardButton]] = []
    for idx, app in enumerate(results):
        app_name = app.get("name", "برنامه")
        # Truncate title if too long for inline button
        display_name = app_name[:24] + ("…" if len(app_name) > 24 else "")
        size_mb = app.get("size_mb", 0)
        size_text = f" ({size_mb} MB)" if size_mb else ""
        btn_label = f"{display_name}{size_text}"

        callback_data = f"dl_soft_{platform_key}_{idx}"
        keyboard.append([InlineKeyboardButton(btn_label, callback_data=callback_data)])

    # Cancel / new search button
    keyboard.append(
        [InlineKeyboardButton("❌ لغو / جستجوی جدید", callback_data="dl_soft_cancel")]
    )

    result_prompt = (
        f"🔍 نتایج جستجو برای: *{query}* ({platform_label})\n\n"
        "👇 لطفاً نرم‌افزار مورد نظر خود را جهت دانلود انتخاب کنید:"
    )

    try:
        await status_msg.edit_text(
            result_prompt,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except Exception:
        await status_msg.delete()
        await update.message.reply_text(
            result_prompt,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )


async def software_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback query handler for software download buttons (pattern: ^dl_soft_)."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    chat_id = str(query.message.chat_id)

    # Handle Cancel button
    if data == "dl_soft_cancel":
        await async_clear_state(chat_id)
        try:
            await query.message.edit_text(
                "❌ جستجو لغو شد.\n"
                "برای جستجوی جدید، نام نرم‌افزار مورد نظر را از منو انتخاب کنید."
            )
        except Exception:
            pass
        return

    # Parse callback data: dl_soft_{platform}_{index}
    match = re.match(r"^dl_soft_([a-z]+)_(\d+)$", data)
    if not match:
        await query.message.reply_text("❌ درخواست نامعتبر است.")
        return

    platform_key = match.group(1)
    try:
        item_index = int(match.group(2))
    except ValueError:
        await query.message.reply_text("❌ شناسه نامعتبر است.")
        return

    # Retrieve cached results
    results: List[Dict[str, Any]] = (
        _software_cache.get(str(chat_id))
        or (context.bot_data.get("software") or {}).get(chat_id)
        or (await async_get_state(chat_id)).get("software_results")
        or []
    )

    if not results or item_index >= len(results):
        await query.message.reply_text(
            "⚠️ نشست منقضی شده است یا اطلاعات یافت نشد. لطفاً مجدداً نام نرم‌افزار را جستجو کنید."
        )
        return

    app = results[item_index]
    app_name = app.get("name", "نرم‌افزار")
    version = app.get("version", "نامشخص")
    download_url = app.get("download_url")
    updated = app.get("updated", "نامشخص")
    extension = app.get("extension", "bin")
    estimated_size_mb = app.get("size_mb", 0)

    if not download_url:
        await query.message.reply_text("❌ متأسفانه لینک دانلود مستقیم برای این نرم‌افزار در دسترس نیست.")
        return

    # Guard against huge files exceeding max limit
    if estimated_size_mb and estimated_size_mb > MAX_ALLOWED_MB:
        await query.message.reply_text(
            f"⚠️ حجم این نرم‌افزار ({estimated_size_mb} مگابایت) بیش از سقف مجاز دانلود ربات ({MAX_ALLOWED_MB} مگابایت) است.\n\n"
            f"🔗 می‌توانید آن را مستقیماً از لینک زیر دانلود فرمایید:\n{download_url}",
            disable_web_page_preview=True,
        )
        return

    user_id = str(query.from_user.id) if query.from_user else chat_id
    async with user_action_lock(user_id, "software_dl", timeout_sec=15) as acquired:
        if not acquired:
            await query.message.reply_text("⏳ درخواست دانلود قبلی شما در حال ثبت است. لطفاً صبر کنید.")
            return

        # Immediately disable inline buttons to prevent spam/double-tap
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        try:
            await query.message.edit_text(
                f"⏳ در حال پردازش و دانلود نرم‌افزار «{app_name}»...\n"
                "لطفاً شکیبا باشید."
            )
        except Exception:
            pass

    await async_clear_state(chat_id)
    track_task(
        _process_software_download(
            context=context,
            chat_id=chat_id,
            platform_key=platform_key,
            item_index=item_index,
            app=app,
        ),
        name=f"software_dl_{chat_id}",
    )


async def _process_software_download(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    platform_key: str,
    item_index: int,
    app: Dict[str, Any],
) -> None:
    app_name = app.get("name", "نرم‌افزار")
    version = app.get("version", "نامشخص")
    download_url = app["download_url"]
    updated = app.get("updated", "نامشخص")
    extension = app.get("extension", "bin")
    platform_fa = "اندروید (Android)" if platform_key == "android" else "ویندوز (Windows)"

    # Download & package under concurrency semaphore; release semaphore before Bale upload
    async with async_temp_dir(prefix="soft_dl_") as tmp_dir:
        package = app.get("package", "")
        raw_id = package or app_name
        ascii_base = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_id).strip('_')
        ascii_base = re.sub(r'_+', '_', ascii_base)
        if not ascii_base or len(ascii_base) < 2:
            ascii_base = f"software_{platform_key}_{item_index + 1}"

        clean_ver = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(version)) or "1.0"
        safe_base = f"{ascii_base}_v{clean_ver}"
        file_name = f"{safe_base}.{extension}"

        async with _DOWNLOAD_SEMAPHORE:
            try:
                downloaded_path = await SoftwareService.download_file(
                    url=download_url,
                    dest_dir=tmp_dir,
                    filename=file_name,
                )
            except ValueError as ve:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {ve}\n🔗 لینک مستقیم: {download_url}",
                    disable_web_page_preview=True,
                )
                await log_upload_failed("software", chat_id)
                return
            except Exception as e:
                logger.exception("Failed to download software '%s': %s", app_name, e)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ خطا در دانلود فایل از سرور منبع. لطفاً بعداً تلاش کنید یا نرم‌افزار دیگری را امتحان کنید.",
                )
                await log_upload_failed("software", chat_id)
                return

            if not await asyncio.to_thread(os.path.isfile, downloaded_path):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ فایل دانلود شده یافت نشد.",
                )
                await log_upload_failed("software", chat_id)
                return

            file_size = await get_file_size_async(downloaded_path)
            file_size_mb = file_size / (1024 * 1024)

            if file_size > MAX_BALE_SEND_BYTES:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"📦 حجم این برنامه ({file_size_mb:.1f} MB) بیش از سقف مجاز پیام‌رسان بله است.\n"
                        "⚙️ در حال فشرده‌سازی و پارت‌بندی خودکار فایل در پس‌زمینه..."
                    ),
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚙️ در حال آماده‌سازی و ساخت فایل ZIP جهت ارسال بدون محدودیت به بله...",
                )

            zips_dir = os.path.join(tmp_dir, "zips")
            # Split directly at MAX_BALE_SEND_BYTES (40 MB) in a single pass
            part_paths, archive_base, split_method = await asyncio.to_thread(
                build_zip_and_split,
                input_path=downloaded_path,
                out_dir=zips_dir,
                zip_basename=safe_base,
                max_part_bytes=MAX_BALE_SEND_BYTES,
            )
            total_parts = len(part_paths)

        if total_parts == 1:
            zip_file = part_paths[0]
            zip_size_mb = (await get_file_size_async(zip_file)) / (1024 * 1024)
            caption = (
                f"📦 **{app_name}**\n\n"
                f"🔖 **نسخه:** `{version}`\n"
                f"💾 **حجم فایل (ZIP):** `{zip_size_mb:.1f} MB`\n"
                f"📅 **تاریخ بروزرسانی:** `{updated}`\n"
                f"💻 **سیستم‌عامل:** {platform_fa}\n\n"
                "📁 **راهنما:** نرم‌افزار به صورت فایل زیپ (ZIP) ارسال شد تا محدودیت امنیتی بله رفع شود. پس از دانلود، فایل را استخراج (Extract) فرمایید."
            )
            try:
                zip_name = os.path.basename(zip_file)
                doc_input = await load_input_file(zip_file, filename=zip_name)
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc_input,
                    filename=zip_name,
                    caption=caption,
                    parse_mode="Markdown",
                    write_timeout=180,
                    read_timeout=120,
                    connect_timeout=60,
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ نرم‌افزار با موفقیت ارسال شد!\nبرای جستجوی برنامه‌ای دیگر، مجدداً نام آن را بنویسید.",
                )
                await log_upload_success("software", chat_id)
            except Exception as e:
                logger.exception("Failed to send software document to chat %s: %s", chat_id, e)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ خطا در ارسال فایل به بله. لطفاً مجدداً امتحان کنید.",
                )
                await log_upload_failed("software", chat_id)
        else:
            for part_idx, part_path in enumerate(part_paths, 1):
                part_size_mb = (await get_file_size_async(part_path)) / (1024 * 1024)
                part_caption = (
                    f"📦 **{app_name}** (پارت {part_idx} از {total_parts})\n"
                    f"🔖 **نسخه:** `{version}`\n"
                    f"💾 **حجم این پارت:** `{part_size_mb:.1f} MB`\n"
                    f"💻 **سیستم‌عامل:** {platform_fa}"
                )
                try:
                    part_name = os.path.basename(part_path)
                    part_input = await load_input_file(part_path, filename=part_name)
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=part_input,
                        filename=part_name,
                        caption=part_caption,
                        parse_mode="Markdown",
                        write_timeout=180,
                        read_timeout=120,
                        connect_timeout=60,
                    )
                except Exception as e:
                    logger.exception("Failed sending part %d of %s: %s", part_idx, app_name, e)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ خطا در ارسال پارت {part_idx}. فرآیند متوقف شد.",
                    )
                    await log_upload_failed("software", chat_id)
                    return

            # Send merge instructions
            instructions = format_merge_instructions(archive_base, total_parts, split_method)
            if instructions:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=instructions,
                    parse_mode="Markdown",
                )

            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ تمام پارت‌های نرم‌افزار با موفقیت ارسال شدند!",
            )
            await log_upload_success("software", chat_id)
