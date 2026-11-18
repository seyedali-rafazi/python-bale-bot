# handlers/states/state_tiktok.py

import os
import asyncio
import re
import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)
from core.state_manager import set_state
from core.task_utils import remove_file_async, track_task
from core.constants import BTN_BACK
from services.rate_limiter import user_action_lock
from services.tiktok import (
    download_tiktok_video,
    search_tiktok_videos,
    get_tiktok_trends,
)
from core.database import (
    is_vip,
    get_tt_downloads,
    increment_tt_downloads,
    log_upload_failed,
)
from core.limits import get_limit


DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)


def _strip_hashtags(text: str) -> str:
    if not text:
        return ""
    # Remove hashtags like #us, #something, including Persian/Unicode word chars
    cleaned = re.sub(r"(?:^|\s)#[^\s#]+", " ", text, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def check_tt_dl_limit(update: Update, user_id: str) -> bool:
    vip, current_dl = await asyncio.gather(
        is_vip(user_id),
        get_tt_downloads(user_id),
    )
    max_dl = get_limit("tiktok_download", vip)

    if current_dl >= max_dl:
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه تیک‌تاک شما به پایان رسیده است."
        )
        return False

    return True


async def _safe_edit_text(msg, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass


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
    file_path = None

    try:
        async with DOWNLOAD_SEMAPHORE:
            await _safe_edit_text(status_msg, "⬇️ در حال دریافت ویدیو...")
            file_path = await download_tiktok_video(url)

        if not file_path or not os.path.exists(file_path):
            await _safe_edit_text(status_msg, "❌ متاسفانه دانلود این ویدیو با خطا مواجه شد.")
            await log_upload_failed("tiktok", user_id)
            return

        safe_title = _strip_hashtags(title) or "tiktok_video"
        display_name = f"{safe_title}.mp4" if not safe_title.endswith(".mp4") else safe_title
        caption = f"✅ {safe_title}"

        await _safe_edit_text(status_msg, "📤 ویدیو دانلود شد! در حال ارسال...")

        with open(file_path, "rb") as vid:
            await context.bot.send_video(
                chat_id=chat_id,
                video=vid,
                filename=display_name,
                caption=caption,
                read_timeout=300,
                write_timeout=300,
            )

        await increment_tt_downloads(user_id)

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        print(f"❌ TikTok Error: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="❌ خطایی در پردازش رخ داد."
        )
        await log_upload_failed("tiktok", user_id)
    finally:
        if file_path:
            await remove_file_async(file_path)


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

        async with user_action_lock(user_id_str, "tiktok_dl", timeout_sec=10) as acquired:
            if not acquired:
                await update.message.reply_text("⏳ درخواست قبلی شما در حال ثبت است. لطفاً صبر کنید.")
                return
            if not await check_tt_dl_limit(update, user_id_str):
                return

            track_task(
                background_tt_download(
                    context, text, chat_id, user_id_str, "دانلود مستقیم با لینک"
                ),
                name=f"tiktok_link_{chat_id}",
            )
        return

    elif step == "waiting_tt_search":
        await update.message.reply_text("⏳ در حال جستجو...")

        results = await search_tiktok_videos(text, max_results=10)

        if not results:
            logger.warning("[TikTok] Search returned 0 results for query '%s' from user %s", text, user_id_str)
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

                async with user_action_lock(user_id_str, "tiktok_dl", timeout_sec=10) as acquired:
                    if not acquired:
                        await update.message.reply_text("⏳ درخواست قبلی شما در حال ثبت است. لطفاً صبر کنید.")
                        return
                    if not await check_tt_dl_limit(update, user_id_str):
                        return

                    selected_video = videos[index]
                    track_task(
                        background_tt_download(
                            context,
                            selected_video["url"],
                            chat_id,
                            user_id_str,
                            selected_video["title"],
                        ),
                        name=f"tiktok_sel_{chat_id}",
                    )

            except ValueError:
                await update.message.reply_text("❌ فرمت شماره اشتباه است.")
        return
