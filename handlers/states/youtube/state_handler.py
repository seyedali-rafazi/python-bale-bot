import asyncio
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from core.state_manager import set_state
from core.constants import BTN_YT_VIDEO, BTN_YT_AUDIO, BTN_BACK, is_s3_enabled
from core.keyboards import (
    get_yt_format_keyboard,
    get_yt_delivery_keyboard,
    get_yt_quality_telegram_keyboard,
)
from services.youtube import async_search_yt_videos, get_video_info_cached
from core.yt_moderation import (
    MSG_BLOCKED_CHANNEL,
    MSG_BLOCKED_SEARCH,
    is_search_query_blocked,
    check_channel_allowed,
    check_video_info_allowed,
)
from .callbacks import (
    DELIVERY_PROMPT_TEXT,
    _quality_prompt,
    build_yt_destination_keyboard,
    create_yt_link_session,
)
from .helpers import check_user_limit


async def _send_yt_post_format_prompt(
    message,
    chat_id: str,
    url: str,
    format_type: str,
    *,
    use_token: bool = False,
) -> None:
    if is_s3_enabled():
        if use_token:
            token = create_yt_link_session(chat_id, yt_url=url, format_type=format_type)
            keyboard = build_yt_destination_keyboard(token=token)
        else:
            set_state(chat_id, "waiting_yt_destination", yt_url=url, format=format_type)
            keyboard = build_yt_destination_keyboard()
        await message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=keyboard,
        )
        return

    # S3 غیرفعال است: مستقیم برای آپلود به بله ادامه می‌دهیم بدون پرسیدن مقصد
    if format_type == "video":
        if use_token:
            token = create_yt_link_session(
                chat_id,
                yt_url=url,
                format_type=format_type,
                step="waiting_yt_delivery",
                destination="telegram",
            )
        else:
            token = None
            set_state(
                chat_id,
                "waiting_yt_delivery",
                yt_url=url,
                format=format_type,
                destination="telegram",
            )
        await message.reply_text(
            DELIVERY_PROMPT_TEXT,
            reply_markup=get_yt_delivery_keyboard(token=token),
            parse_mode="Markdown",
        )
        return

    if use_token:
        token = create_yt_link_session(
            chat_id,
            yt_url=url,
            format_type=format_type,
            step="waiting_yt_quality",
            destination="telegram",
            delivery_mode="zip",
        )
    else:
        token = None
        set_state(
            chat_id,
            "waiting_yt_quality",
            yt_url=url,
            format=format_type,
            destination="telegram",
            delivery_mode="zip",
        )
    await message.reply_text(
        _quality_prompt(format_type),
        reply_markup=get_yt_quality_telegram_keyboard(token=token),
    )


async def handle_youtube_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_yt_last5_channel":
        raw_ch = text.strip()
        if "youtube.com/" in raw_ch:
            raw_ch = raw_ch.rstrip("/").split("/")[-1]
        channel = raw_ch.lstrip("@").strip()
        if not channel:
            await update.message.reply_text("❌ آیدی کانال نامعتبر است.")
            return
        if not await check_channel_allowed(channel):
            await update.message.reply_text(MSG_BLOCKED_CHANNEL)
            return
        url = f"https://www.youtube.com/@{channel}/videos"
        await update.message.reply_text("⏳ در حال دریافت لیست ویدیوها...")
        try:
            results = await async_search_yt_videos(url, 5)
        except Exception:
            await update.message.reply_text("❌ خطا در دریافت لیست ویدیوها. لطفاً دوباره تلاش کنید.")
            return

        if not results:
            await update.message.reply_text("❌ کانال پیدا نشد یا ویدیویی ندارد.")
            return

        res_text = f"🎥 ۵ ویدیوی آخر کانال {channel}:\n\n"
        keyboard = []

        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])

        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_yt_selection", videos=results)
        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    elif step == "waiting_yt_global_search":
        if await is_search_query_blocked(text):
            await update.message.reply_text(MSG_BLOCKED_SEARCH)
            return
        await update.message.reply_text("⏳ در حال جستجو...")
        try:
            results = await async_search_yt_videos(text, 10)
        except Exception:
            await update.message.reply_text("❌ خطا در جستجوی یوتیوب. لطفاً دوباره تلاش کنید.")
            return

        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🌍 نتایج جستجو برای `{text}`:\n\n"
        keyboard = []

        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            if i % 2 != 0:
                keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])
            else:
                keyboard[-1].append(KeyboardButton(f"📥 دانلود ویدیو {i}"))

        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_yt_selection", videos=results)
        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    elif step == "waiting_yt_ch_search_name":
        if not await check_channel_allowed(text):
            await update.message.reply_text(MSG_BLOCKED_CHANNEL)
            return
        set_state(chat_id, "waiting_yt_ch_search_query", channel=text)
        await update.message.reply_text(
            "حالا کلمه کلیدی یا نام ویدیویی که در این کانال دنبالش هستید را بفرستید:"
        )
        return

    elif step == "waiting_yt_ch_search_query":
        channel = state_data.get("channel", "").replace("@", "")
        query = text

        if await is_search_query_blocked(query):
            await update.message.reply_text(MSG_BLOCKED_SEARCH)
            return

        await update.message.reply_text("⏳ در حال جستجو در کانال...")
        search_query = f"{channel} {query}"
        try:
            results = await async_search_yt_videos(search_query, 5)
        except Exception:
            await update.message.reply_text("❌ خطا در جستجوی کانال. لطفاً دوباره تلاش کنید.")
            return

        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🔎 نتایج جستجو:\n\n"
        keyboard = []

        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            keyboard.append([KeyboardButton(f"📥 دانلود ویدیو {i}")])

        keyboard.append([KeyboardButton(BTN_BACK)])

        set_state(chat_id, "waiting_yt_selection", videos=results)
        await update.message.reply_text(
            res_text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    elif step == "waiting_yt_selection":
        if text.startswith("📥 دانلود ویدیو "):
            if not await check_user_limit(chat_id):
                await update.message.reply_text(
                    "❌ محدودیت دانلود روزانه شما ($ 1 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
                )
                return

            try:
                index = int(text.replace("📥 دانلود ویدیو ", "").strip()) - 1
                videos = state_data.get("videos", [])

                if index < 0 or index >= len(videos):
                    await update.message.reply_text(
                        f"❌ شماره نامعتبر است. لطفاً عددی بین 1 تا {len(videos)} وارد کنید."
                    )
                    return

                selected_video = videos[index]

                set_state(
                    chat_id,
                    "waiting_yt_format",
                    yt_url=selected_video["url"],
                )
                await update.message.reply_text(
                    "✅ ویدیو انتخاب شد! فرمت را انتخاب کنید 👇",
                    reply_markup=get_yt_format_keyboard(),
                )

            except ValueError:
                await update.message.reply_text("❌ فرمت شماره اشتباه است.")
            except Exception as e:
                print(f"❌ Error: {e}")
                await update.message.reply_text("❌ خطایی در انتخاب ویدیو رخ داد.")
        return

    elif step == "waiting_yt_link":
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        dl_format = state_data.get("format")
        if dl_format and not await check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 1 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        status_msg = await update.message.reply_text("⏳ در حال بررسی لینک...")

        try:
            info = await get_video_info_cached(text)
        except Exception as e:
            print(f"get_video_info error: {e}")
            try:
                await status_msg.delete()
            except Exception:
                pass
            await update.message.reply_text(
                "❌ خطا در دریافت اطلاعات ویدیو. لطفاً دوباره تلاش کنید."
            )
            return

        try:
            await status_msg.delete()
        except Exception:
            pass

        if not info:
            await update.message.reply_text(
                "❌ ویدیو پیدا نشد یا یوتیوب در دسترس نیست. لینک را بررسی کنید."
            )
            return

        if not await check_video_info_allowed(info):
            await update.message.reply_text(MSG_BLOCKED_CHANNEL)
            return

        if not dl_format:
            set_state(chat_id, "waiting_yt_format", yt_url=text)
            await update.message.reply_text(
                "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        set_state(chat_id, "waiting_yt_link", format=dl_format)
        await _send_yt_post_format_prompt(
            update.message, chat_id, text, dl_format, use_token=True
        )
        return

    elif step == "waiting_yt_format":
        url = state_data.get("yt_url")
        if not url:
            await update.message.reply_text(
                "❌ لینک منقضی شده. دوباره از منو لینک را ارسال کنید."
            )
            return

        if text not in (BTN_YT_VIDEO, BTN_YT_AUDIO):
            await update.message.reply_text(
                "لطفاً یکی از دکمه‌های «دانلود ویدیو» یا «دانلود MP3» را بزنید.",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        if not await check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 1 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        format_type = "video" if text == BTN_YT_VIDEO else "audio"

        await _send_yt_post_format_prompt(
            update.message, chat_id, url, format_type, use_token=False
        )
        return
