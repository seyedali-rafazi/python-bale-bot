import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from services.http_client import get_http_session
from telegram.ext import ContextTypes
from core.database import get_gh_downloads, increment_gh_downloads, is_vip
from core.state_manager import clear_state
import uuid
import os

# ==================== سیستم صف ====================
download_queue = asyncio.Queue()
worker_started = False


async def download_worker():
    """ورکری که درخواست‌های درون صف را یکی‌یکی پردازش می‌کند"""
    while True:
        func, args = await download_queue.get()
        try:
            await func(*args)
        except Exception as e:
            print(f"Queue Worker Error: {e}")
        finally:
            download_queue.task_done()


async def enqueue_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id, repo_path, user_id
):
    """اضافه کردن درخواست به صف"""
    global worker_started
    if not worker_started:
        asyncio.create_task(download_worker())
        worker_started = True

    position = download_queue.qsize()
    await context.bot.send_message(
        chat_id, f"⏳ درخواست شما در صف قرار گرفت. (نفرات قبل از شما: $ {position} $)"
    )

    # ارسال به صف
    await download_queue.put(
        (process_github_download, (update, context, chat_id, repo_path, user_id))
    )


# ==================================================


async def handle_github_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
    text: str,
    chat_id: str,
    state_data: dict,
):

    user_id = update.effective_user.id
    vip_status = await is_vip(str(user_id))
    max_dl = 20 if vip_status else 4

    downloads_count = await get_gh_downloads(str(user_id))
    if downloads_count >= max_dl:
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
        )
        await clear_state(chat_id)
        return

    if step == "waiting_gh_dl":
        repo_path = text.replace("https://github.com/", "").strip()
        # به جای پردازش مستقیم، به صف اضافه می‌کنیم
        await enqueue_download(update, context, chat_id, repo_path, str(user_id))

    elif step == "waiting_gh_user":
        await update.message.reply_text("⏳ در حال دریافت اطلاعات کاربر...")
        session = await get_http_session()
        async with session.get(
            f"https://api.github.com/users/{text}/repos?sort=updated&per_page=10",
            timeout=60,
        ) as resp:
            if resp.status == 200:
                repos = await resp.json()
                msg = f"📂 ۱۰ ریپازیتوری آخر {text}:\n\n"
                keyboard = []
                for i, repo in enumerate(repos):
                    msg += f"{i + 1}. {repo['name']}\n"
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                f"📥 دانلود {repo['name']}",
                                callback_data=f"ghdl_{repo['full_name']}",
                            )
                        ]
                    )

                await update.message.reply_text(
                    msg, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text("❌ کاربر یافت نشد.")

    elif step == "waiting_gh_search":
        await update.message.reply_text("⏳ در حال جستجو در گیت‌هاب...")
        session = await get_http_session()
        async with session.get(
            f"https://api.github.com/search/repositories?q={text}&per_page=10",
            timeout=60,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                repos = data.get("items", [])
                if not repos:
                    await update.message.reply_text("❌ نتیجه‌ای یافت نشد.")
                    return

                msg = f"🔍 ۱۰ نتیجه برتر برای «{text}»:\n\n"
                keyboard = []
                for i, repo in enumerate(repos):
                    msg += f"{i + 1}. {repo['full_name']} (⭐ {repo['stargazers_count']})\n"
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                f"📥 دانلود {repo['name']}",
                                callback_data=f"ghdl_{repo['full_name']}",
                            )
                        ]
                    )

                await update.message.reply_text(
                    msg, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text("❌ خطا در ارتباط با گیت‌هاب.")


async def process_github_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id, repo_path, user_id
):
    await context.bot.send_message(
        chat_id, "⏳ نوبت شما رسید! در حال آماده‌سازی فایل..."
    )

    zip_url = f"https://github.com/{repo_path}/archive/HEAD.zip"
    screenshot_url = (
        f"https://image.thum.io/get/width/1080/crop/800/https://github.com/{repo_path}"
    )

    file_name = f"{repo_path.replace('/', '_')}.zip"
    temp_path = f"temp_{uuid.uuid4().hex}_{file_name}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        session = await get_http_session()
        try:
            await asyncio.wait_for(
                context.bot.send_photo(
                    chat_id=chat_id,
                    photo=screenshot_url,
                    caption=f"📸 نمای کلی از ریپازیتوری: {repo_path}",
                ),
                timeout=5.0,
            )
        except Exception:
            pass

        async with session.get(
            zip_url, headers=headers, allow_redirects=True, timeout=120
        ) as resp:
            if resp.status == 200:
                downloaded_size = 0
                is_oversized = False
                max_bytes = 20 * 1024 * 1024  # محدودیت 20 مگابایت

                with open(temp_path, "wb") as f:
                    # دانلود تکه‌تکه برای کنترل حجم در حین دانلود
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        downloaded_size += len(chunk)
                        if downloaded_size > max_bytes:
                            is_oversized = True
                            break
                        f.write(chunk)

                if is_oversized:
                    await context.bot.send_message(
                        chat_id,
                        "❌ بله پشتیبانی نمیشه (حجم فایل بالای ۲۰ مگابایت است).",
                    )
                else:
                    file_size_mb = downloaded_size / (1024 * 1024)
                    if file_size_mb < 0.001:
                        await context.bot.send_message(
                            chat_id,
                            "❌ فایل دریافتی نامعتبر است (احتمالاً ریپازیتوری وجود ندارد یا پرایوت است).",
                        )
                    else:
                        await context.bot.send_document(
                            chat_id=chat_id, document=temp_path, filename=file_name
                        )
                        await increment_gh_downloads(user_id)
            else:
                await context.bot.send_message(
                    chat_id,
                    f"❌ خطایی در دریافت فایل رخ داد. (کد خطا: {resp.status})",
                )
    except Exception as e:
        await context.bot.send_message(chat_id, "❌ خطا در پردازش یا آپلود فایل.")
        print(f"GitHub Error: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        await clear_state(chat_id)


async def github_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    user_id = str(query.from_user.id)

    if data.startswith("ghdl_"):
        repo_path = data.split("ghdl_")[1]
        vip_status = await is_vip(user_id)
        max_dl = 20 if vip_status else 4

        downloads_count = await get_gh_downloads(user_id)
        if downloads_count >= max_dl:
            await query.message.reply_text(
                "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
            )
            return

        # به جای پردازش مستقیم، به صف اضافه می‌کنیم
        await enqueue_download(update, context, chat_id, repo_path, user_id)
