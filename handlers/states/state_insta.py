# handlers/states/state_insta.py

import os
import asyncio
import shutil
from telegram import Update
from telegram.ext import ContextTypes
from services.instagram import (
    download_instagram,
    get_latest_post,
)

# ایجاد محدودکننده برای جلوگیری از فشار به سرور و بن شدن IP (مثلا حداکثر 5 دانلود همزمان)
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

        processing_msg = await update.message.reply_text(
            "⏳ در حال دانلود از اینستاگرام... لطفا کمی صبر کنید"
        )

        async with INSTA_SEMAPHORE:  # ورود به صف دانلود
            try:
                file_path = await asyncio.wait_for(
                    asyncio.to_thread(download_instagram, text), timeout=60.0
                )

                if file_path and os.path.exists(file_path):
                    try:
                        # کتابخانه telegram به صورت خودکار مسیر رشته‌ای (String) را به صورت Async می‌خواند (نیازی به with open نیست)
                        if file_path.endswith(".mp4"):
                            await context.bot.send_video(
                                chat_id=chat_id, video=file_path
                            )
                        else:
                            await context.bot.send_document(
                                chat_id=chat_id, document=file_path
                            )
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    await processing_msg.delete()
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
        return

    elif step == "waiting_ig_last_post":
        processing_msg = await update.message.reply_text(
            "⏳ در حال بررسی پیج و دانلود آخرین پست..."
        )

        async with INSTA_SEMAPHORE:
            try:
                # حالا تابع دو خروجی می‌دهد: مسیر فایل مدیا، و مسیر پوشه موقت برای حذف
                file_path, target_dir = await asyncio.wait_for(
                    get_latest_post(text), timeout=60.0
                )

                if file_path and os.path.exists(file_path):
                    try:
                        if file_path.endswith(".mp4"):
                            await context.bot.send_video(
                                chat_id=chat_id, video=file_path
                            )
                        else:
                            await context.bot.send_photo(
                                chat_id=chat_id, photo=file_path
                            )
                    finally:
                        # حذف کامل پوشه اختصاصی کاربر (شامل تمام فایل‌های json و txt جانبی)
                        if target_dir and os.path.exists(target_dir):
                            shutil.rmtree(target_dir, ignore_errors=True)
                    await processing_msg.delete()
                else:
                    if target_dir and os.path.exists(target_dir):
                        shutil.rmtree(target_dir, ignore_errors=True)
                    await processing_msg.edit_text(
                        "❌ پست پیدا نشد. آیا مطمئنید پیج پابلیک است؟"
                    )

            except asyncio.TimeoutError:
                await processing_msg.edit_text("⏳ زمان درخواست به پایان رسید.")
            except Exception as e:
                print(f"Insta Last Post Error: {e}")
                await processing_msg.edit_text("❌ خطای غیرمنتظره‌ای رخ داد.")
        return
