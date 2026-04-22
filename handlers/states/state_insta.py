import os
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.instagram import download_instagram


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

        try:
            # اجرای دانلود در Thread جداگانه با حداکثر زمان 60 ثانیه برای جلوگیری از هنگ کردن ربات
            file_path = await asyncio.wait_for(
                asyncio.to_thread(download_instagram, text), timeout=60.0
            )

            if file_path and os.path.exists(file_path):
                try:
                    if file_path.endswith(".mp4"):
                        with open(file_path, "rb") as vid:
                            await context.bot.send_video(chat_id=chat_id, video=vid)
                    else:
                        with open(file_path, "rb") as doc:
                            await context.bot.send_document(
                                chat_id=chat_id, document=doc
                            )
                finally:
                    # حذف فایل پس از ارسال
                    if os.path.exists(file_path):
                        os.remove(file_path)

                # حذف پیام "در حال دانلود..." پس از ارسال موفق
                await processing_msg.delete()
            else:
                await processing_msg.edit_text(
                    "❌ دانلود شکست خورد. ممکن است پیج پرایوت باشد."
                )

        except asyncio.TimeoutError:
            await processing_msg.edit_text(
                "⏳ زمان درخواست به پایان رسید (بیش از ۶۰ ثانیه). لطفا مجددا تلاش کنید."
            )
        except Exception as e:
            print(f"Insta DL Error: {e}")
            await processing_msg.edit_text("❌ خطای غیرمنتظره‌ای در حین دانلود رخ داد.")

        return
