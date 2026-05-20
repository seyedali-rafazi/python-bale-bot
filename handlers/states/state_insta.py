# handlers/states/state_insta.py

import os
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.instagram import download_instagram
from core.database import (
    get_available_cloud_mb,
    reduce_cloud_storage,
    add_cloud_file,
)

try:
    from services.parspack_s3 import upload_to_s3
except ImportError:
    upload_to_s3 = None

INSTA_SEMAPHORE = asyncio.Semaphore(5)


async def handle_insta_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    if step == "waiting_ig_link":
        if "instagram.com" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        keyboard = [
            [
                InlineKeyboardButton("📱 بله", callback_data=f"ig_dl_tel_{text}"),
                InlineKeyboardButton(
                    "☁️ فضای ابری", callback_data=f"ig_dl_cloud_{text}"
                ),
            ]
        ]

        await update.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def background_download_insta_link(
    context, chat_id, link: str, destination: str = "telegram"
):
    processing_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ در حال دانلود از اینستاگرام... لطفا کمی صبر کنید",
    )

    async with INSTA_SEMAPHORE:
        file_path = None
        try:
            file_path = await asyncio.wait_for(
                asyncio.to_thread(download_instagram, link), timeout=60.0
            )

            if file_path and os.path.exists(file_path):
                if destination == "server":
                    user_storage_mb = await get_available_cloud_mb(chat_id)
                    if user_storage_mb is None or user_storage_mb <= 0:
                        user_storage_mb = 0

                    file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)

                    if user_storage_mb <= 0 or file_size_mb > user_storage_mb:
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

                    s3_url = await asyncio.to_thread(
                        upload_to_s3,
                        file_path,
                        None,
                        progress_dict,
                    )

                    if s3_url:
                        file_size_mb = round(
                            os.path.getsize(file_path) / (1024 * 1024), 2
                        )
                        file_name = os.path.basename(file_path)

                        await add_cloud_file(chat_id, file_name, file_size_mb, s3_url)
                        await reduce_cloud_storage(chat_id, file_size_mb)

                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ فایل با موفقیت در فضای ابری ذخیره شد:\n\n📉 حجم کسر شده: {file_size_mb} مگابایت\n⏳ لینک دانلود تا 3 ساعت معتبر است.\n\n🔗 [لینک دانلود]({s3_url})",
                            parse_mode="Markdown",
                        )
                        try:
                            await processing_msg.delete()
                        except Exception:
                            pass
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="❌ خطا در آپلود ابری.",
                        )

                else:
                    try:
                        if file_path.endswith(".mp4"):
                            await context.bot.send_video(
                                chat_id=chat_id, video=file_path
                            )
                        else:
                            await context.bot.send_document(
                                chat_id=chat_id, document=file_path
                            )
                    finally:
                        pass

                    try:
                        await processing_msg.delete()
                    except Exception:
                        pass
            else:
                await processing_msg.edit_text(
                    "❌ دانلود شکست خورد. ممکن است پیج پرایوت باشد."
                )

        except asyncio.TimeoutError:
            await processing_msg.edit_text(
                "⏳ زمان درخواست به پایان رسید (بیش از ۶۰ ثانیه)."
            )
        except Exception as e:
            print(f"Insta DL Error: {e}")
            await processing_msg.edit_text("❌ خطای غیرمنتظره‌ای رخ داد.")
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass


async def handle_insta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    chat_id = str(update.effective_chat.id)

    if data.startswith("ig_dl_tel_"):
        link = data.split("ig_dl_tel_", 1)[1]
        asyncio.create_task(
            background_download_insta_link(
                context, chat_id, link, destination="telegram"
            )
        )

    elif data.startswith("ig_dl_cloud_"):
        link = data.split("ig_dl_cloud_", 1)[1]
        asyncio.create_task(
            background_download_insta_link(context, chat_id, link, destination="server")
        )
