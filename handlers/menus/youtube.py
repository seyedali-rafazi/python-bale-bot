import json
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import RetryAfter

from core.state_manager import set_state
from core.keyboards import get_youtube_menu_keyboard, get_back_only_keyboard
from core.database import get_setting, get_top_cached_videos
from core.task_utils import track_task
from handlers.ensure_membership import ensure_membership
from handlers.states.youtube.bale_send import (
    _BALE_SEND_TIMEOUTS,
    chat_send_lock,
    pause_between_parts,
)
from services.rate_limiter import user_action_lock

logger = logging.getLogger(__name__)


async def btn_yt_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return

    if await get_setting("youtube_enabled", "1") == "0":
        await update.message.reply_text(
            "❌ بخش یوتیوب فعلاً توسط ادمین غیرفعال شده است."
        )
        return

    await update.message.reply_text(
        "📺 به بخش پیشرفته یوتیوب خوش آمدید. یک گزینه را انتخاب کنید:",
        reply_markup=get_youtube_menu_keyboard(),
    )


async def btn_yt_last5_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_last5_channel")
    await update.message.reply_text(
        "آیدی یا نام کاربری کانال یوتیوب را بفرستید (مثال: mrbeast@ یا mrbeast):",
        reply_markup=get_back_only_keyboard(),
    )


async def btn_yt_ch_search_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_ch_search_name")
    await update.message.reply_text(
        "ابتدا آیدی کانال مورد نظر را بفرستید (مثال: mrbeast@):",
        reply_markup=get_back_only_keyboard(),
    )


async def btn_yt_global_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_global_search")
    await update.message.reply_text(
        "موضوع یا نام ویدیوی مورد نظر خود را برای جستجو بفرستید:",
        reply_markup=get_back_only_keyboard(),
    )


async def btn_yt_link_vid_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_link", format="video")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیو یوتیوب را برای دانلود (تصویری) ارسال کنید:",
        reply_markup=get_back_only_keyboard(),
    )


async def btn_yt_link_mp3_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    chat_id = str(update.effective_chat.id)
    set_state(chat_id, "waiting_yt_link", format="audio")
    await update.message.reply_text(
        "🔗 لطفاً لینک ویدیو یوتیوب را برای تبدیل به فایل صوتی (MP3) ارسال کنید:",
        reply_markup=get_back_only_keyboard(),
    )


async def _send_top_videos_task(context: ContextTypes.DEFAULT_TYPE, chat_id, top_videos) -> None:
    async with user_action_lock(str(chat_id), "yt_top_videos", timeout_sec=60) as acquired:
        if not acquired:
            return
        async with chat_send_lock(str(chat_id)):
            total_videos = len(top_videos)
            for index, video in enumerate(top_videos):
                try:
                    file_ids = json.loads(video["file_ids"])
                    views = video["view_count"]
                    video_id = video["video_id"]
                    fmt = (video.get("format_type") or "").lower()

                    async def _send_part(fid: str, cap: str):
                        if "zip" in fmt or fmt == "document":
                            await context.bot.send_document(
                                chat_id=chat_id, document=fid, caption=cap, **_BALE_SEND_TIMEOUTS
                            )
                        elif fmt == "audio":
                            await context.bot.send_audio(
                                chat_id=chat_id, audio=fid, caption=cap, **_BALE_SEND_TIMEOUTS
                            )
                        else:
                            await context.bot.send_video(
                                chat_id=chat_id, video=fid, caption=cap, **_BALE_SEND_TIMEOUTS
                            )

                    if file_ids:
                        total_parts = len(file_ids)

                        for part_index, file_id in enumerate(file_ids):
                            if total_parts > 1:
                                caption = (
                                    f"🏅 رتبه: {index + 1} (پارت {part_index + 1} از {total_parts})\n"
                                    f"👁 بازدید: {views}\n"
                                    f"🔗 آیدی ویدیو: {video_id}"
                                )
                            else:
                                caption = (
                                    f"🏅 رتبه: {index + 1}\n"
                                    f"👁 بازدید: {views}\n"
                                    f"🔗 آیدی ویدیو: {video_id}"
                                )

                            is_last = (index == total_videos - 1) and (part_index == total_parts - 1)
                            part_ok = True
                            try:
                                await _send_part(file_id, caption)
                            except RetryAfter as e:
                                logger.warning("Rate limited! Sleeping for %ss", e.retry_after)
                                await asyncio.sleep(max(1, int(e.retry_after)) + 1)
                                try:
                                    await _send_part(file_id, caption)
                                except Exception as retry_err:
                                    part_ok = False
                                    logger.warning(
                                        "Error sending top video %s part %s after RetryAfter: %s",
                                        video_id,
                                        part_index + 1,
                                        retry_err,
                                    )
                            except Exception as part_err:
                                part_ok = False
                                logger.warning(
                                    "Error sending top video %s part %s: %s",
                                    video_id,
                                    part_index + 1,
                                    part_err,
                                )
                            if not is_last:
                                await pause_between_parts(extra_sec=0.0 if part_ok else 1.5)

                except Exception as e:
                    logger.warning("Error sending top video %s: %s", video.get("video_id", "Unknown"), e)
                    continue


async def btn_yt_top_videos_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_membership(update, context):
        return
    top_videos = await get_top_cached_videos(4)

    if not top_videos:
        await update.message.reply_text("📭 هنوز ویدیویی در کش سیستم ثبت نشده است.")
        return

    await update.message.reply_text(
        "🔥 در حال ارسال 4 ویدیوی پربازدید سیستم...\nلطفاً کمی صبر کنید."
    )

    chat_id = update.effective_chat.id
    track_task(
        _send_top_videos_task(context, chat_id, top_videos),
        name=f"yt_top_{chat_id}",
    )
