# handlers/states/state_insta.py

import os
import asyncio
import logging
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.state_manager import StateCache, set_state
from core.task_utils import bounded_large_upload, get_file_size_async, load_input_file, remove_file_async, track_task
from handlers.utils import safe_answer_query, safe_edit_or_reply

logger = logging.getLogger(__name__)
_ig_link_cache = StateCache(max_capacity=2000, default_ttl=3600.0)
from services.instagram import async_download_instagram
from services.rate_limiter import user_action_lock
from core.database import (
    get_available_cloud_mb,
    reserve_cloud_quota,
    release_cloud_quota,
    record_cloud_upload,
    log_upload_success,
    log_upload_failed,
)

from core.constants import is_s3_enabled

try:
    from services.parspack_s3 import async_upload_to_s3_with_key, upload_to_s3_with_key
except ImportError:
    async_upload_to_s3_with_key = None
    upload_to_s3_with_key = None


MAX_BALE_MEDIA_BYTES = 50 * 1024 * 1024

INSTA_SEMAPHORE = asyncio.Semaphore(5)


async def start_insta_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    link: str,
    chat_id: str,
    *,
    keep_state: bool = True,
) -> None:
    clean_link = link.strip()
    if keep_state:
        set_state(chat_id, "waiting_ig_link")

    if not is_s3_enabled():
        user = getattr(update, "effective_user", None)
        user_id = str(user.id) if user else chat_id
        async with user_action_lock(user_id, "insta_dl", timeout_sec=10) as acquired:
            if not acquired:
                await update.message.reply_text(
                    "⏳ درخواست شما در حال پردازش است. لطفاً صبر کنید."
                )
                return
            track_task(
                background_download_insta_link(
                    context, chat_id, clean_link, destination="telegram"
                ),
                name=f"insta_tel_{chat_id}",
            )
        return

    token = uuid.uuid4().hex[:12]
    _ig_link_cache[token] = clean_link

    keyboard = [
        [
            InlineKeyboardButton("📱 بله", callback_data=f"ig_dl_tel_{token}"),
            InlineKeyboardButton(
                "☁️ فضای ابری", callback_data=f"ig_dl_cloud_{token}"
            ),
        ]
    ]

    await update.message.reply_text(
        "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_insta_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_ig_link":
        if "instagram.com" not in text and "instagr.am" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        await start_insta_download(update, context, text, chat_id, keep_state=True)


async def background_download_insta_link(
    context, chat_id, link: str, destination: str = "telegram"
):
    processing_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ در حال دانلود از اینستاگرام... لطفا کمی صبر کنید",
    )

    file_path = None
    try:
        async with INSTA_SEMAPHORE:
            file_path = await async_download_instagram(link, timeout_sec=60.0)

        if file_path and await asyncio.to_thread(os.path.exists, file_path):
            if destination == "server":
                file_size_mb = round((await get_file_size_async(file_path)) / (1024 * 1024), 2)
                reserved = await reserve_cloud_quota(chat_id, file_size_mb)
                if not reserved:
                    user_storage_mb = await get_available_cloud_mb(chat_id)
                    if user_storage_mb is None or user_storage_mb <= 0:
                        user_storage_mb = 0
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"❌ فضای ابری شما کافی نیست!\n\n"
                            f"حجم فایل: {file_size_mb} مگابایت\n"
                            f"فضای باقیمانده شما: {round(user_storage_mb, 2)} مگابایت\n\n"
                            f"لطفاً برای ارتقای حجم ابری خود از طریق منوی فروشگاه اقدام کنید."
                        ),
                    )
                    return

            try:
                await processing_msg.edit_text(
                    "📤 دانلود تکمیل شد! در حال آپلود..."
                )
            except Exception:
                pass

            if destination == "server":
                progress_dict = {"text": "شروع آپلود ابری...", "is_finished": False}

                try:
                    if async_upload_to_s3_with_key is not None:
                        s3_url, s3_key = await async_upload_to_s3_with_key(
                            file_path,
                            None,
                            progress_dict,
                            upload_fn=upload_to_s3_with_key,
                        )
                    else:
                        s3_url, s3_key = await asyncio.to_thread(
                            upload_to_s3_with_key,
                            file_path,
                            None,
                            progress_dict,
                        )
                except BaseException:
                    await release_cloud_quota(chat_id, file_size_mb)
                    raise

                if s3_url:
                    file_name = os.path.basename(file_path)

                    await record_cloud_upload(
                        chat_id,
                        file_name,
                        file_size_mb,
                        s3_url,
                        s3_key=s3_key,
                        quota_reserved=True,
                    )

                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ فایل با موفقیت در فضای ابری ذخیره شد:\n\n📉 حجم کسر شده: {file_size_mb} مگابایت\n⏳ لینک دانلود تا 3 ساعت معتبر است.\n\n🔗 [لینک دانلود]({s3_url})",
                        parse_mode="Markdown",
                    )
                    await log_upload_success("instagram", chat_id)
                    try:
                        await processing_msg.delete()
                    except Exception:
                        pass
                else:
                    await release_cloud_quota(chat_id, file_size_mb)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ خطا در آپلود ابری.",
                    )
                    await log_upload_failed("instagram", chat_id)

            else:
                file_size_bytes = await get_file_size_async(file_path)
                if file_size_bytes > MAX_BALE_MEDIA_BYTES:
                    size_mb = round(file_size_bytes / (1024 * 1024), 1)
                    extra_hint = (
                        "\nمی‌توانید برای ارسال فایل‌های بزرگ‌تر از گزینه «☁️ فضای ابری» استفاده کنید."
                        if is_s3_enabled()
                        else ""
                    )
                    await processing_msg.edit_text(
                        f"❌ حجم فایل ({size_mb} مگابایت) از سقف مجاز پیام‌رسان بله (۵۰ مگابایت) بیشتر است.{extra_hint}"
                    )
                    await log_upload_failed("instagram", chat_id)
                    return

                async with bounded_large_upload():
                    media_input = await load_input_file(file_path)
                    try:
                        if file_path.endswith(".mp4"):
                            await context.bot.send_video(
                                chat_id=chat_id, video=media_input
                            )
                        else:
                            await context.bot.send_document(
                                chat_id=chat_id, document=media_input
                            )
                    finally:
                        del media_input
                await log_upload_success("instagram", chat_id)

                try:
                    await processing_msg.delete()
                except Exception:
                    pass
        else:
            await processing_msg.edit_text(
                "❌ دانلود شکست خورد. ممکن است پیج پرایوت باشد."
            )
            await log_upload_failed("instagram", chat_id)

    except asyncio.TimeoutError:
        await safe_edit_or_reply(
            processing_msg,
            "⏳ زمان درخواست به پایان رسید (بیش از ۶۰ ثانیه).",
        )
        await log_upload_failed("instagram", chat_id)
    except Exception as e:
        print(f"Insta DL Error: {e}")
        await safe_edit_or_reply(processing_msg, "❌ خطای غیرمنتظره‌ای رخ داد.")
        await log_upload_failed("instagram", chat_id)
    finally:
        await remove_file_async(file_path)


async def handle_insta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)

    data = query.data
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)

    async with user_action_lock(user_id, "insta_dl", timeout_sec=10) as acquired:
        if not acquired:
            await query.message.reply_text("⏳ درخواست شما در حال پردازش است. لطفاً صبر کنید.")
            return

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        def _resolve_ig_link(raw_payload: str) -> str | None:
            if raw_payload.startswith(("http://", "https://")):
                return raw_payload
            return _ig_link_cache.get(raw_payload)

        if data.startswith("ig_dl_tel_"):
            link = _resolve_ig_link(data.split("ig_dl_tel_", 1)[1])
            if not link:
                await query.message.reply_text("❌ نشست منقضی شده است. لطفاً لینک را دوباره بفرستید.")
                return
            track_task(
                background_download_insta_link(
                    context, chat_id, link, destination="telegram"
                ),
                name=f"insta_tel_{chat_id}",
            )

        elif data.startswith("ig_dl_cloud_"):
            if not is_s3_enabled():
                await query.message.reply_text("❌ آپلود در فضای ابری در حال حاضر غیرفعال است.")
                return
            link = _resolve_ig_link(data.split("ig_dl_cloud_", 1)[1])
            if not link:
                await query.message.reply_text("❌ نشست منقضی شده است. لطفاً لینک را دوباره بفرستید.")
                return
            track_task(
                background_download_insta_link(context, chat_id, link, destination="server"),
                name=f"insta_cloud_{chat_id}",
            )
