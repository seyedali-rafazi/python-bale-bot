# handlers/states/state_tiktok.py

import os
import asyncio
import re
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import BTN_BACK
from services.tiktok import (
    download_tiktok_video,
    search_tiktok_videos,
    get_tiktok_trends,
)
from core.database import (
    is_vip,
    get_tt_downloads,
    increment_tt_downloads,
    add_tiktok_explore_video,
)
from core.limits import get_limit
from services.zip_utils import build_zip_and_split


STORAGE_CHANNEL_ID = "@digittt"
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)


def _strip_hashtags(text: str) -> str:
    if not text:
        return ""
    # Remove hashtags like #us, #something, including Persian/Unicode word chars
    cleaned = re.sub(r"(?:^|\s)#[^\s#]+", " ", text, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def check_tt_dl_limit(update: Update, user_id: str) -> bool:
    vip = await is_vip(user_id)  # اضافه شدن await
    max_dl = get_limit("tiktok_download", vip)
    current_dl = await get_tt_downloads(user_id)  # اضافه شدن await

    if current_dl >= max_dl:
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه تیک‌تاک شما به پایان رسیده است."
        )
        return False

    return True


# پارامتر user_id اضافه شد
async def background_tt_download(
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    chat_id: str,
    user_id: str,
    title: str = "ویدیوی تیک‌تاک",
):
    status_msg = await context.bot.send_message(
        chat_id=chat_id, text="⏳ در صف انتظار برای دانلود..."
    )

    try:
        async with DOWNLOAD_SEMAPHORE:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="⬇️ در حال دریافت ویدیو...",
            )

            file_path = await download_tiktok_video(url)

            if not file_path or not os.path.exists(file_path):
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text="❌ متاسفانه دانلود این ویدیو با خطا مواجه شد.",
                )
                return

            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="📤 ویدیو دانلود شد! در حال آپلود در سرور...",
            )

            # Build ZIP for user delivery (20MB parts)
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="📦 در حال ساخت ZIP و تقسیم به پارت‌های 20MB...",
            )

            safe_title = _strip_hashtags(title) or "tiktok_video"
            zip_basename = "tiktok_video"
            zip_path, zip_parts = await asyncio.to_thread(
                build_zip_and_split,
                file_path,
                os.path.dirname(file_path) or ".",
                zip_basename,
                20 * 1024 * 1024,
            )

            # Upload ZIP parts to storage channel too (no tags)
            channel_file_ids = []
            total_parts = len(zip_parts)
            for idx, part_path in enumerate(zip_parts, 1):
                caption = (
                    f"📦 TikTok ZIP\n{safe_title}\nPart {idx}/{total_parts}"
                    if safe_title
                    else f"📦 TikTok ZIP\nPart {idx}/{total_parts}"
                )
                with open(part_path, "rb") as doc:
                    channel_msg = await context.bot.send_document(
                        chat_id=STORAGE_CHANNEL_ID,
                        document=doc,
                        caption=caption,
                        read_timeout=300,
                        write_timeout=300,
                    )
                    channel_file_ids.append(channel_msg.document.file_id)

            # Store first part id for explore DB (backward compatibility)
            if channel_file_ids:
                await add_tiktok_explore_video(channel_file_ids[0])

        # Send ZIP parts to user
        total_parts = len(zip_parts)
        if total_parts > 1:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📦 فایل ZIP آماده شد (شامل {total_parts} پارت). در حال ارسال...",
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text="📦 فایل ZIP آماده شد. در حال ارسال...")

        for idx, part_path in enumerate(zip_parts, 1):
            if total_parts > 1:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📤 ارسال پارت {idx} از {total_parts}...",
                )
            with open(part_path, "rb") as doc:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc,
                    caption=f"✅ {safe_title or 'TikTok'}\n📦 ZIP Part {idx}/{total_parts}",
                    read_timeout=300,
                    write_timeout=300,
                )

        # افزایش محدودیت کاربر فقط در اینجا (پس از ارسال موفق) انجام می‌شود
        await increment_tt_downloads(user_id)  # اضافه شدن await

        await context.bot.delete_message(
            chat_id=chat_id, message_id=status_msg.message_id
        )

    except Exception as e:
        print(f"❌ TikTok Error: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="❌ خطایی در پردازش رخ داد."
        )
    finally:
        # cleanup zip artifacts
        try:
            if "zip_parts" in locals():
                for p in zip_parts:
                    if p and os.path.exists(p) and p != file_path:
                        os.remove(p)
            if "zip_path" in locals() and zip_path and os.path.exists(zip_path):
                # zip_path might be included in zip_parts; safe to ignore errors
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
        except Exception:
            pass
        if "file_path" in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)


async def process_tiktok_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text("⏳ در حال دریافت ویدیوهای ترند...")

    results = await get_tiktok_trends()
    if not results:
        await update.message.reply_text("❌ ویدیویی یافت نشد.")
        return

    res_text = "🔥 ویدیوهای ترند تیک‌تاک:\n\n"
    keyboard = []
    for i, vid in enumerate(results, 1):
        res_text += f"{i}️⃣ {vid['title']}\n\n"
        keyboard.append([KeyboardButton(f"📥 دانلود تیک‌تاک {i}")])
    keyboard.append([KeyboardButton(BTN_BACK)])

    set_state(chat_id, "waiting_tt_selection", videos=results)
    await update.message.reply_text(
        res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def handle_tiktok_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    user_id_str = str(update.effective_user.id)

    if step == "waiting_tt_link":
        if "tiktok.com" not in text and "tiktok" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        # فقط چک میکنیم، اما کسر نمیکنیم
        if not await check_tt_dl_limit(update, user_id_str):
            return

        asyncio.create_task(
            # ارسال user_id_str به عنوان آرگومان
            background_tt_download(
                context, text, chat_id, user_id_str, "دانلود مستقیم با لینک"
            )
        )
        return

    elif step == "waiting_tt_search":
        await update.message.reply_text("⏳ در حال جستجو...")

        results = await search_tiktok_videos(text, max_results=10)

        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🔍 نتایج جستجو برای `{text}`:\n\n"
        keyboard = []
        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            if i % 2 != 0:
                keyboard.append([KeyboardButton(f"📥 دانلود تیک‌تاک {i}")])
            else:
                keyboard[-1].append(KeyboardButton(f"📥 دانلود تیک‌تاک {i}"))

        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_tt_selection", videos=results)
        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    elif step == "waiting_tt_selection":
        if text.startswith("📥 دانلود تیک‌تاک "):
            try:
                index = int(text.replace("📥 دانلود تیک‌تاک ", "").strip()) - 1
                videos = state_data.get("videos", [])

                if index < 0 or index >= len(videos):
                    await update.message.reply_text(
                        f"❌ لطفاً عددی بین $1$ تا ${len(videos)}$ وارد کنید."
                    )
                    return

                # فقط چک میکنیم، کسر نمیکنیم
                if not await check_tt_dl_limit(update, user_id_str):
                    return

                selected_video = videos[index]
                asyncio.create_task(
                    # ارسال user_id_str به عنوان آرگومان
                    background_tt_download(
                        context,
                        selected_video["url"],
                        chat_id,
                        user_id_str,
                        selected_video["title"],
                    )
                )

            except ValueError:
                await update.message.reply_text("❌ فرمت شماره اشتباه است.")
        return
