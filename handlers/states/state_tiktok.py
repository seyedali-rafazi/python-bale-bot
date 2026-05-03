# handlers/states/state_tiktok.py
import os
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import BTN_BACK
from services.tiktok import (
    download_tiktok_video,
    search_tiktok_videos,
    get_tiktok_trends,
)

# نام کانالی که ویدیوها به عنوان آرشیو در آن ذخیره می‌شوند
STORAGE_CHANNEL_ID = "@digiacharstorage"


async def background_tt_download(
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    chat_id: str,
    title: str = "ویدیوی تیک‌تاک",
):
    status_msg = await context.bot.send_message(
        chat_id=chat_id, text="⏳ در حال دریافت ویدیوی تیک‌تاک..."
    )

    try:
        # 1. دانلود ویدیو
        file_path = await asyncio.to_thread(download_tiktok_video, url)

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

        # 2. ذخیره در کانال آرشیو (اکسپلور داخلی) و دریافت file_id
        with open(file_path, "rb") as vid:
            channel_msg = await context.bot.send_video(
                chat_id=STORAGE_CHANNEL_ID,
                video=vid,
                caption=f"🎥 اکسپلور داخلی تیک‌تاک\n🔗 لینک اصلی: {url}",
                read_timeout=300,
                write_timeout=300,
            )
            file_id = channel_msg.video.file_id

        # 3. ارسال file_id برای کاربر نهایی (سرعت بالا در ارسال)
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=f"✅ {title}\n🤖 دانلود شده توسط ربات",
        )

        # پاک کردن پیام صبر کنید
        await context.bot.delete_message(
            chat_id=chat_id, message_id=status_msg.message_id
        )

    except Exception as e:
        print(f"❌ TikTok Error: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="❌ خطایی در پردازش رخ داد."
        )
    finally:
        # 4. حذف فایل از هارد سرور
        if "file_path" in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)


async def process_tiktok_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه ترند تیک‌تاک"""
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text("⏳ در حال دریافت ویدیوهای ترند...")

    results = await asyncio.to_thread(get_tiktok_trends)
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

    # 1. گرفتن لینک مستقیم تیک‌تاک
    if step == "waiting_tt_link":
        # تغییر در این خط انجام شده است
        if "tiktok" not in text.lower():
            await update.message.reply_text(
                "❌ لینک نامعتبر است. لطفاً یک لینک معتبر از تیک‌تاک ارسال کنید."
            )
            return

        asyncio.create_task(background_tt_download(context, text, chat_id))
        return

    # 2. گرفتن موضوع و جستجو ($10$ ویدیو)
    elif step == "waiting_tt_search":
        await update.message.reply_text("⏳ در حال جستجو...")
        results = await asyncio.to_thread(search_tiktok_videos, text, max_results=10)

        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🔍 نتایج جستجو برای `{text}`:\n\n"
        keyboard = []
        for i, vid in enumerate(results, 1):
            res_text += f"{i}️⃣ {vid['title']}\n\n"
            # چینش دکمه‌ها (دو تا در هر ردیف)
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

    # 3. انتخاب ویدیو از لیست جستجو یا ترند
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

                selected_video = videos[index]
                asyncio.create_task(
                    background_tt_download(
                        context, selected_video["url"], chat_id, selected_video["title"]
                    )
                )

            except ValueError:
                await update.message.reply_text("❌ فرمت شماره اشتباه است.")
        return
