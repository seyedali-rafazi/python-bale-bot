# handlers/states/state_insta.py

import os
import asyncio
import shutil
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes
from core.state_manager import set_state
from core.constants import BTN_BACK
from services.instagram import (
    download_instagram,
    get_latest_post,
    search_instagram_posts,
    get_instagram_trends,
)
from core.database import (
    get_available_cloud_mb,
    reduce_cloud_storage,
    add_cloud_file,
    is_vip,
    get_ig_downloads,
    increment_ig_downloads,
    add_instagram_explore_media,
)
from core.limits import get_limit

try:
    from services.parspack_s3 import upload_to_s3
except ImportError:
    upload_to_s3 = None

# ایجاد محدودکننده برای جلوگیری از فشار به سرور و بن شدن IP (مثلا حداکثر 5 دانلود همزمان)
INSTA_SEMAPHORE = asyncio.Semaphore(5)


async def check_ig_dl_limit(update: Update, user_id: str) -> bool:
    vip = await is_vip(user_id)
    max_dl = get_limit("instagram_download", vip)
    current_dl = await get_ig_downloads(user_id)

    if current_dl >= max_dl:
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه اینستاگرام شما به پایان رسیده است."
        )
        return False
    return True


async def _store_explore_from_message(sent_msg):
    file_id = None
    if sent_msg.video:
        file_id = sent_msg.video.file_id
    elif sent_msg.photo:
        file_id = sent_msg.photo[-1].file_id
    elif sent_msg.document:
        file_id = sent_msg.document.file_id
    if file_id:
        await add_instagram_explore_media(file_id)


async def process_instagram_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text("⏳ در حال دریافت پست‌های ترند...")

    results = await get_instagram_trends()
    if not results:
        await update.message.reply_text("❌ پستی یافت نشد.")
        return

    res_text = "🔥 پست‌های ترند اینستاگرام:\n\n"
    keyboard = []
    for i, post in enumerate(results, 1):
        res_text += f"{i}️⃣ {post['title']}\n\n"
        keyboard.append([KeyboardButton(f"📥 دانلود اینستاگرام {i}")])
    keyboard.append([KeyboardButton(BTN_BACK)])

    set_state(chat_id, "waiting_ig_selection", videos=results)
    await update.message.reply_text(
        res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def handle_insta_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):
    user_id_str = str(update.effective_user.id)

    if step == "waiting_ig_link":
        if "instagram.com" not in text:
            await update.message.reply_text("❌ لینک نامعتبر است.")
            return

        if not await check_ig_dl_limit(update, user_id_str):
            return

        # ===================================
        # نمایش گزینه‌های مقصد
        # ===================================
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

    elif step == "waiting_ig_last_post":
        # ===================================
        # نمایش گزینه‌های مقصد برای آخرین پست
        # ===================================
        keyboard = [
            [
                InlineKeyboardButton("📱 بله", callback_data=f"ig_last_tel_{text}"),
                InlineKeyboardButton(
                    "☁️ فضای ابری", callback_data=f"ig_last_cloud_{text}"
                ),
            ]
        ]

        await update.message.reply_text(
            "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif step == "waiting_ig_search":
        await update.message.reply_text("⏳ در حال جستجو...")

        results = await search_instagram_posts(text, max_results=10)
        if not results:
            await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
            return

        res_text = f"🔍 نتایج جستجو برای `{text}`:\n\n"
        keyboard = []
        for i, post in enumerate(results, 1):
            res_text += f"{i}️⃣ {post['title']}\n\n"
            if i % 2 != 0:
                keyboard.append([KeyboardButton(f"📥 دانلود اینستاگرام {i}")])
            else:
                keyboard[-1].append(KeyboardButton(f"📥 دانلود اینستاگرام {i}"))

        keyboard.append([KeyboardButton(BTN_BACK)])
        set_state(chat_id, "waiting_ig_selection", videos=results)
        await update.message.reply_text(
            res_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    elif step == "waiting_ig_selection":
        if text.startswith("📥 دانلود اینستاگرام "):
            try:
                index = int(text.replace("📥 دانلود اینستاگرام ", "").strip()) - 1
                videos = state_data.get("videos", [])

                if index < 0 or index >= len(videos):
                    await update.message.reply_text(
                        f"❌ لطفاً عددی بین 1 تا {len(videos)} وارد کنید."
                    )
                    return

                if not await check_ig_dl_limit(update, user_id_str):
                    return

                selected = videos[index]
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "📱 بله",
                            callback_data=f"ig_dl_tel_{selected['url']}",
                        ),
                        InlineKeyboardButton(
                            "☁️ فضای ابری",
                            callback_data=f"ig_dl_cloud_{selected['url']}",
                        ),
                    ]
                ]
                await update.message.reply_text(
                    "📍 لطفاً محل آپلود فایل را انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            except ValueError:
                await update.message.reply_text("❌ فرمت شماره اشتباه است.")


# ======================================
# تابع دانلود پس‌زمینه برای لینک
# ======================================
async def background_download_insta_link(
    context, chat_id, link: str, destination: str = "telegram", user_id: str = None
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
                # =====================================
                # چک فضای ابری برای آپلود به سرور
                # =====================================
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

                # =====================================

                try:
                    await processing_msg.edit_text(
                        "📤 دانلود تکمیل شد! در حال آپلود..."
                    )
                except:
                    pass

                # ========================
                # آپلود به سرور ابری
                # ========================
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
                        if user_id:
                            await increment_ig_downloads(user_id)
                        try:
                            await processing_msg.delete()
                        except Exception:
                            pass
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="❌ خطا در آپلود ابری.",
                        )

                # ========================
                # آپلود به بله
                # ========================
                else:
                    try:
                        if file_path.endswith(".mp4"):
                            sent_msg = await context.bot.send_video(
                                chat_id=chat_id, video=file_path
                            )
                        else:
                            sent_msg = await context.bot.send_photo(
                                chat_id=chat_id, photo=file_path
                            )
                        await _store_explore_from_message(sent_msg)
                        if user_id:
                            await increment_ig_downloads(user_id)
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
                except:
                    pass


# ======================================
# تابع دانلود پس‌زمینه برای آخرین پست
# ======================================
async def background_download_insta_last_post(
    context, chat_id, username: str, destination: str = "telegram", user_id: str = None
):
    processing_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ در حال بررسی پیج و دانلود آخرین پست...",
    )

    async with INSTA_SEMAPHORE:
        file_path = None
        target_dir = None
        try:
            file_path, target_dir = await asyncio.wait_for(
                get_latest_post(username), timeout=60.0
            )

            if file_path and os.path.exists(file_path):
                # =====================================
                # چک فضای ابری برای آپلود به سرور
                # =====================================
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

                # =====================================

                try:
                    await processing_msg.edit_text(
                        "📤 دانلود تکمیل شد! در حال آپلود..."
                    )
                except:
                    pass

                # ========================
                # آپلود به سرور ابری
                # ========================
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
                        if user_id:
                            await increment_ig_downloads(user_id)
                        try:
                            await processing_msg.delete()
                        except Exception:
                            pass
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="❌ خطا در آپلود ابری.",
                        )

                # ========================
                # آپلود به بله
                # ========================
                else:
                    try:
                        if file_path.endswith(".mp4"):
                            sent_msg = await context.bot.send_video(
                                chat_id=chat_id, video=file_path
                            )
                        else:
                            sent_msg = await context.bot.send_photo(
                                chat_id=chat_id, photo=file_path
                            )
                        await _store_explore_from_message(sent_msg)
                        if user_id:
                            await increment_ig_downloads(user_id)
                    finally:
                        pass

                    try:
                        await processing_msg.delete()
                    except Exception:
                        pass
            else:
                await processing_msg.edit_text(
                    "❌ پست پیدا نشد. آیا مطمئنید پیج پابلیک است؟"
                )

        except asyncio.TimeoutError:
            await processing_msg.edit_text("⏳ زمان درخواست به پایان رسید.")
        except Exception as e:
            print(f"Insta Last Post Error: {e}")
            await processing_msg.edit_text("❌ خطای غیرمنتظره‌ای رخ داد.")
        finally:
            if target_dir and os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass


# ======================================
# هندلر کال‌بک برای دانلود اینستاگرام
# ======================================
async def handle_insta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    data = query.data
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)

    if data.startswith("ig_dl_tel_"):
        link = data.split("ig_dl_tel_", 1)[1]
        asyncio.create_task(
            background_download_insta_link(
                context, chat_id, link, destination="telegram", user_id=user_id
            )
        )

    elif data.startswith("ig_dl_cloud_"):
        link = data.split("ig_dl_cloud_", 1)[1]
        asyncio.create_task(
            background_download_insta_link(
                context, chat_id, link, destination="server", user_id=user_id
            )
        )

    elif data.startswith("ig_last_tel_"):
        username = data.split("ig_last_tel_", 1)[1]
        asyncio.create_task(
            background_download_insta_last_post(
                context, chat_id, username, destination="telegram", user_id=user_id
            )
        )

    elif data.startswith("ig_last_cloud_"):
        username = data.split("ig_last_cloud_", 1)[1]
        asyncio.create_task(
            background_download_insta_last_post(
                context, chat_id, username, destination="server", user_id=user_id
            )
        )
