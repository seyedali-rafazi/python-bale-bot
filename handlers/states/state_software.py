# handlers/states/state_software.py
"""
Software download state handler and callback query processor.
Manages:
  - Text input in waiting_software_android and waiting_software_windows states
  - Presenting 5 top results with inline buttons
  - Downloading and sending the installer (APK / EXE / ZIP)
  - Auto-splitting into ZIP parts if file exceeds 50 MB (Bale limit)
"""

import logging
import os
import re
import tempfile
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.database.monitoring import log_upload_failed, log_upload_success
from core.state_manager import clear_state, get_state, set_state
from services.software_service import SoftwareService, sanitize_filename
from services.zip_utils import build_zip_and_split, format_merge_instructions

logger = logging.getLogger(__name__)

MAX_BALE_BYTES = 49 * 1024 * 1024  # 49 MB (safety margin under 50 MB Bale limit)


async def handle_software_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: Dict[str, Any],
):
    """Called from states/__init__.py when user enters software query."""
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

    # Cache results in context.bot_data and user_states
    if "software" not in context.bot_data:
        context.bot_data["software"] = {}
    context.bot_data["software"][chat_id] = results

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
        try:
            await query.message.edit_text(
                "❌ جستجو لغو شد.\n"
                "برای جستجوی جدید، نام نرم‌افزار مورد نظر را ارسال کنید یا از منوی پایین استفاده نمایید."
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
        (context.bot_data.get("software") or {}).get(chat_id)
        or get_state(chat_id).get("software_results")
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

    if not download_url:
        await query.message.reply_text("❌ متأسفانه لینک دانلود مستقیم برای این نرم‌افزار در دسترس نیست.")
        return

    # Disable buttons to prevent duplicate downloads
    try:
        await query.message.edit_text(
            f"⏳ در حال دانلود نرم‌افزار «{app_name}»...\n"
            "لطفاً شکیبا باشید، پس از اتمام دانلود فایل ارسال خواهد شد."
        )
    except Exception:
        pass

    platform_fa = "اندروید (Android)" if platform_key == "android" else "ویندوز (Windows)"

    # Download in temporary directory
    with tempfile.TemporaryDirectory(prefix="soft_dl_") as tmp_dir:
        safe_base = sanitize_filename(app_name)
        file_name = f"{safe_base}_v{version}.{extension}"
        file_name = sanitize_filename(file_name)

        try:
            downloaded_path = await SoftwareService.download_file(
                url=download_url,
                dest_dir=tmp_dir,
                filename=file_name,
            )
        except Exception as e:
            logger.exception("Failed to download software '%s': %s", app_name, e)
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ خطا در دانلود فایل از سرور منبع. لطفاً بعداً تلاش کنید یا نرم‌افزار دیگری را امتحان کنید.",
            )
            await log_upload_failed("software", chat_id)
            return

        if not os.path.isfile(downloaded_path):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ فایل دانلود شده یافت نشد.",
            )
            await log_upload_failed("software", chat_id)
            return

        file_size = os.path.getsize(downloaded_path)
        file_size_mb = file_size / (1024 * 1024)

        # Check Bale 50 MB limit
        if file_size <= MAX_BALE_BYTES:
            caption = (
                f"📦 **{app_name}**\n\n"
                f"🔖 **نسخه:** `{version}`\n"
                f"💾 **حجم:** `{file_size_mb:.1f} MB`\n"
                f"📅 **تاریخ بروزرسانی:** `{updated}`\n"
                f"💻 **سیستم‌عامل:** {platform_fa}"
            )
            try:
                with open(downloaded_path, "rb") as fh:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=fh,
                        filename=os.path.basename(downloaded_path),
                        caption=caption,
                        parse_mode="Markdown",
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
            # File > 50 MB: Zip & Split into parts
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"📦 حجم این برنامه ({file_size_mb:.1f} MB) بیش از سقف ۵۰ مگابایت پیام‌رسان بله است.\n"
                    "⚙️ در حال فشرده‌سازی و پارت‌بندی خودکار فایل..."
                ),
            )

            zips_dir = os.path.join(tmp_dir, "zips")
            part_paths, archive_base, split_method = build_zip_and_split(
                input_path=downloaded_path,
                out_dir=zips_dir,
                zip_basename=safe_base,
                max_part_bytes=MAX_BALE_BYTES,
            )

            total_parts = len(part_paths)
            for part_idx, part_path in enumerate(part_paths, 1):
                part_size_mb = os.path.getsize(part_path) / (1024 * 1024)
                part_caption = (
                    f"📦 **{app_name}** (پارت {part_idx} از {total_parts})\n"
                    f"🔖 **نسخه:** `{version}`\n"
                    f"💾 **حجم این پارت:** `{part_size_mb:.1f} MB`\n"
                    f"💻 **سیستم‌عامل:** {platform_fa}"
                )
                try:
                    with open(part_path, "rb") as pf:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=pf,
                            filename=os.path.basename(part_path),
                            caption=part_caption,
                            parse_mode="Markdown",
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
