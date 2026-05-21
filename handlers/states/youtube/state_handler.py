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
from core.constants import BTN_YT_VIDEO, BTN_YT_AUDIO, BTN_BACK
from core.keyboards import get_yt_format_keyboard
from services.youtube import search_yt_videos, get_video_info
from core.yt_moderation import (
    MSG_BLOCKED_CHANNEL,
    MSG_BLOCKED_SEARCH,
    is_search_query_blocked,
    check_channel_allowed,
    check_video_info_allowed,
)
from .helpers import check_user_limit


async def handle_youtube_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_yt_last5_channel":
        channel = text.replace("@", "")
        if not await check_channel_allowed(channel):
            await update.message.reply_text(MSG_BLOCKED_CHANNEL)
            return
        url = f"https://www.youtube.com/@{channel}/videos"
        await update.message.reply_text("⏳ در حال دریافت لیست ویدیوها...")
        results = await asyncio.to_thread(search_yt_videos, url, 5)

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
        results = await asyncio.to_thread(search_yt_videos, text, 10)

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
        results = await asyncio.to_thread(search_yt_videos, search_query, 5)

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
                    "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
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
                await update.message.reply_text(f"❌ خطا: {str(e)}")
        return

    elif step == "waiting_yt_link":
        if "youtube.com" not in text and "youtu.be" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        status_msg = await update.message.reply_text("⏳ در حال بررسی لینک...")

        try:
            info = await asyncio.to_thread(get_video_info, text)
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

        dl_format = state_data.get("format")

        if not dl_format:
            set_state(chat_id, "waiting_yt_format", yt_url=text)
            await update.message.reply_text(
                "✅ لینک دریافت شد! فرمت را انتخاب کنید 👇",
                reply_markup=get_yt_format_keyboard(),
            )
            return

        if not await check_user_limit(chat_id):
            await update.message.reply_text(
                "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        set_state(chat_id, "waiting_yt_destination", yt_url=text, format=dl_format)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 آپلود مستقیم (بله)",
                        callback_data="ytdest_telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "☁️ آپلود در سرور ابری (ویژه Pro ⭐️)",
                        callback_data="ytdest_server",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=keyboard,
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
                "❌ محدودیت دانلود روزانه شما ($ 2 $ ویدیو برای عادی، $ 20 $ ویدیو برای VIP) به پایان رسیده است."
            )
            return

        format_type = "video" if text == BTN_YT_VIDEO else "audio"

        set_state(chat_id, "waiting_yt_destination", yt_url=url, format=format_type)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 آپلود مستقیم (بله)",
                        callback_data="ytdest_telegram",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "☁️ آپلود در سرور ابری (ویژه Pro ⭐️)",
                        callback_data="ytdest_server",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=keyboard,
        )
        return
