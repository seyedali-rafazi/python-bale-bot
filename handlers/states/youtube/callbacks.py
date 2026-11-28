import asyncio
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import StateCache, set_state, async_get_state, clear_state
from core.task_utils import track_task
from services.rate_limiter import user_action_lock
from core.keyboards import (
    get_yt_quality_telegram_keyboard,
    get_yt_quality_server_keyboard,
    get_yt_delivery_keyboard,
    get_main_menu_keyboard,
)
from core.constants import is_s3_enabled
from core.database import is_vip, increment_yt_downloads
from services.youtube import get_video_filesize_cached
from .helpers import check_user_limit
from .task import background_yt_download

_yt_link_sessions = StateCache(max_capacity=2000, default_ttl=3600.0)

DELIVERY_PROMPT_TEXT = (
    "📦 نحوه ارسال ویدیو در بله را انتخاب کنید:\n\n"
    "• **ZIP**: ذخیره در کش سرور و ارسال به صورت فایل فشرده\n"
    "• **ویدیو (MP4)**: ارسال مستقیم بدون ذخیره در کش"
)


def create_yt_link_session(
    chat_id: str,
    yt_url: str,
    format_type: str | None,
    *,
    step: str = "waiting_yt_destination",
    destination: str | None = None,
    delivery_mode: str | None = None,
) -> str:
    token = uuid.uuid4().hex[:12]
    data = {
        "chat_id": str(chat_id),
        "step": step,
        "yt_url": yt_url,
        "format": format_type,
    }
    if destination is not None:
        data["destination"] = destination
    if delivery_mode is not None:
        data["delivery_mode"] = delivery_mode
    _yt_link_sessions[token] = data
    return token


def build_yt_destination_keyboard(token: str | None = None) -> InlineKeyboardMarkup:
    suffix = f"_{token}" if token else ""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📤 آپلود مستقیم (بله)",
                    callback_data=f"ytdest_telegram{suffix}",
                )
            ],
            [
                InlineKeyboardButton(
                    "☁️ آپلود در سرور ابری (ویژه Pro ⭐️)",
                    callback_data=f"ytdest_server{suffix}",
                )
            ],
        ]
    )


async def _load_yt_session(chat_id: str, token: str | None) -> dict | None:
    if token:
        session = _yt_link_sessions.get(token)
        if not session or str(session.get("chat_id")) != str(chat_id):
            return None
        return dict(session)
    return await async_get_state(chat_id)


def _save_yt_session(chat_id: str, token: str | None, step: str, **kwargs) -> None:
    if token:
        data = {"chat_id": str(chat_id), "step": step}
        data.update(kwargs)
        _yt_link_sessions[token] = data
    else:
        set_state(chat_id, step, **kwargs)


def _finish_yt_session(chat_id: str, token: str | None) -> None:
    if token:
        _yt_link_sessions.pop(token, None)
    else:
        clear_state(chat_id)


def _quality_prompt(format_type: str) -> str:
    if format_type == "audio":
        return "🎵 کیفیت صوت را انتخاب کنید (محدودیت: 1 گیگابایت):"
    return "🎥 کیفیت ویدیو را انتخاب کنید (محدودیت: 1 گیگابایت):"


async def youtube_format_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    data = query.data or ""
    chat_id = str(query.message.chat_id)

    parts = data.split("_", 2)
    if len(parts) < 3 or parts[0] != "ytfmt" or parts[1] not in ("video", "audio"):
        return
    format_type = parts[1]
    token = parts[2] or None

    user_state = await _load_yt_session(chat_id, token)
    if not user_state or user_state.get("step") != "waiting_yt_format":
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    if not await check_user_limit(chat_id):
        _finish_yt_session(chat_id, token)
        await query.edit_message_text(
            "❌ محدودیت دانلود روزانه شما ($ 1 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
        )
        return

    url = user_state.get("yt_url")
    if is_s3_enabled():
        _save_yt_session(
            chat_id,
            token,
            "waiting_yt_destination",
            yt_url=url,
            format=format_type,
        )
        await query.edit_message_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=build_yt_destination_keyboard(token=token),
        )
        return

    if format_type == "video":
        _save_yt_session(
            chat_id,
            token,
            "waiting_yt_delivery",
            yt_url=url,
            format=format_type,
            destination="telegram",
        )
        await query.edit_message_text(
            DELIVERY_PROMPT_TEXT,
            reply_markup=get_yt_delivery_keyboard(token=token),
            parse_mode="Markdown",
        )
        return

    _save_yt_session(
        chat_id,
        token,
        "waiting_yt_quality",
        yt_url=url,
        format=format_type,
        destination="telegram",
        delivery_mode="zip",
    )
    await query.edit_message_text(
        _quality_prompt(format_type),
        reply_markup=get_yt_quality_telegram_keyboard(token=token),
    )


async def youtube_destination_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    data = query.data or ""
    chat_id = str(query.message.chat_id)

    parts = data.split("_", 2)
    if len(parts) < 2 or parts[0] != "ytdest" or parts[1] not in ("telegram", "server"):
        return
    dest_choice = parts[1]
    token = parts[2] if len(parts) == 3 and parts[2] else None

    user_state = await _load_yt_session(chat_id, token)
    if not user_state or user_state.get("step") != "waiting_yt_destination":
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    url = user_state.get("yt_url")
    format_type = user_state.get("format")

    if dest_choice == "server":
        if not is_s3_enabled():
            _finish_yt_session(chat_id, token)
            await query.edit_message_text(
                "❌ آپلود در فضای ابری در حال حاضر غیرفعال است."
            )
            return
        if not await is_vip(chat_id):
            if token:
                _yt_link_sessions.pop(token, None)
            await query.edit_message_text(
                "❌ این قابلیت فقط مخصوص کاربران ویژه (Pro ⭐️) می‌باشد."
            )
            return
        destination = "server"
        delivery_mode = "zip"
    else:
        destination = "telegram"
        delivery_mode = "zip"

    if destination == "telegram" and format_type == "video":
        _save_yt_session(
            chat_id,
            token,
            "waiting_yt_delivery",
            yt_url=url,
            format=format_type,
            destination=destination,
        )
        await query.edit_message_text(
            DELIVERY_PROMPT_TEXT,
            reply_markup=get_yt_delivery_keyboard(token=token),
            parse_mode="Markdown",
        )
        return

    _save_yt_session(
        chat_id,
        token,
        "waiting_yt_quality",
        yt_url=url,
        format=format_type,
        destination=destination,
        delivery_mode=delivery_mode,
    )

    keyboard = get_yt_quality_telegram_keyboard(token=token)

    await query.edit_message_text(
        _quality_prompt(format_type), reply_markup=keyboard
    )


async def youtube_delivery_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Error answering callback query: {e}")

    data = query.data or ""
    chat_id = str(query.message.chat_id)

    parts = data.split("_", 2)
    if len(parts) < 2 or parts[0] != "ytdel" or parts[1] not in ("zip", "video"):
        return
    del_choice = parts[1]
    token = parts[2] if len(parts) == 3 and parts[2] else None

    user_state = await _load_yt_session(chat_id, token)
    if not user_state or user_state.get("step") != "waiting_yt_delivery":
        await query.edit_message_text(
            "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
        )
        return

    delivery_mode = "zip" if del_choice == "zip" else "video"
    url = user_state.get("yt_url")
    format_type = user_state.get("format")
    destination = user_state.get("destination", "telegram")

    _save_yt_session(
        chat_id,
        token,
        "waiting_yt_quality",
        yt_url=url,
        format=format_type,
        destination=destination,
        delivery_mode=delivery_mode,
    )

    await query.edit_message_text(
        _quality_prompt(format_type),
        reply_markup=get_yt_quality_telegram_keyboard(token=token),
    )


async def youtube_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    chat_id = str(query.message.chat_id)

    if not data.startswith("ytqual_"):
        try:
            await query.answer()
        except Exception:
            pass
        return

    parts = data.split("_", 2)
    quality = parts[1] if len(parts) >= 2 else ""
    token = parts[2] if len(parts) == 3 and parts[2] else None
    if quality not in {"360", "480", "720", "1080", "best", "bestaudio"}:
        try:
            await query.answer("کیفیت نامعتبر است.")
        except Exception:
            pass
        return
    user_id = str(query.from_user.id) if query.from_user else chat_id

    async with user_action_lock(user_id, "yt_qual", timeout_sec=30) as acquired:
        if not acquired:
            try:
                await query.answer("⏳ در حال پردازش... لطفا صبر کنید.")
            except Exception:
                pass
            return

        try:
            await query.answer()
        except Exception as e:
            print(f"⚠️ Error answering callback query: {e}")

        user_state = await _load_yt_session(chat_id, token)
        if not user_state or user_state.get("step") not in [
            "waiting_yt_quality",
            "processing_yt_quality",
        ]:
            await query.edit_message_text(
                "❌ درخواست شما منقضی شده است. لطفا مجددا لینک را ارسال کنید."
            )
            return

        if user_state.get("step") == "processing_yt_quality":
            await query.message.reply_text("⏳ در حال پردازش... لطفا صبر کنید.")
            return

        if not await check_user_limit(chat_id):
            _finish_yt_session(chat_id, token)
            await query.edit_message_text(
                "❌ محدودیت دانلود روزانه شما به پایان رسیده است."
            )
            return

        url = user_state.get("yt_url")
        format_type = user_state.get("format")
        destination = user_state.get("destination")
        delivery_mode = user_state.get("delivery_mode", "zip")

        _save_yt_session(
            chat_id,
            token,
            "processing_yt_quality",
            yt_url=url,
            format=format_type,
            destination=destination,
            delivery_mode=delivery_mode,
        )

        try:
            await query.edit_message_text(
                "⏳ در حال بررسی کیفیت، لطفا صبر کنید...", reply_markup=None
            )
        except Exception:
            pass

        try:
            if format_type == "video":
                estimated_size = await get_video_filesize_cached(url, quality)
            else:
                estimated_size = await get_video_filesize_cached(url, "bestaudio")

            limit = 1 * 1024 * 1024 * 1024

            if estimated_size and estimated_size > limit:
                size_mb = round(estimated_size / (1024 * 1024), 1)
                msg = (
                    f"❌ فایل حدود {size_mb} مگابایت است و بیشتر از 1 گیگابایت (1024 مگابایت) می‌باشد. "
                    "لطفاً کیفیت پایین‌تری انتخاب کنید."
                )
                keyboard = get_yt_quality_telegram_keyboard(token=token)

                _save_yt_session(
                    chat_id,
                    token,
                    "waiting_yt_quality",
                    yt_url=url,
                    format=format_type,
                    destination=destination,
                    delivery_mode=delivery_mode,
                )
                await query.edit_message_text(msg, reply_markup=keyboard)
                return
        except Exception as e:
            print(f"⚠️ Error checking filesize: {e}")
            keyboard = get_yt_quality_telegram_keyboard(token=token)
            _save_yt_session(
                chat_id,
                token,
                "waiting_yt_quality",
                yt_url=url,
                format=format_type,
                destination=destination,
                delivery_mode=delivery_mode,
            )
            await query.edit_message_text(
                "⚠️ خطا در محاسبه حجم فایل. لطفا دوباره یک کیفیت انتخاب کنید.",
                reply_markup=keyboard,
            )
            return

        await query.edit_message_text("✅ درخواست ثبت شد. در حال انتقال به صف دانلود...")

        _finish_yt_session(chat_id, token)

        if not token:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔙 بازگشت به منوی اصلی",
                reply_markup=get_main_menu_keyboard(),
            )

        await increment_yt_downloads(chat_id)

        track_task(
            background_yt_download(
                context,
                url,
                chat_id,
                format_type,
                destination,
                quality=quality,
                delivery_mode=delivery_mode,
                estimated_size=estimated_size,
            ),
            name=f"yt_dl_{chat_id}",
        )
