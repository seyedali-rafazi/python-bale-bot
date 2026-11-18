import asyncio
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from services.http_client import get_http_session
from telegram.ext import ContextTypes
from core.database import get_gh_downloads, increment_gh_downloads, is_vip
from core.limits import get_limit
from core.state_manager import StateCache, clear_state
from core.task_utils import (
    FileTooLargeError,
    load_input_file,
    remove_file_async,
    stream_aiohttp_to_file,
)
import uuid
import os

# ==================== سیستم صف ====================
GITHUB_WORKERS = max(1, int(os.getenv("GITHUB_WORKERS", "3")))
GITHUB_QUEUE_MAXSIZE = max(10, int(os.getenv("GITHUB_QUEUE_MAXSIZE", "100")))
GITHUB_TEMP_DIR = os.path.join("downloads", "github")
download_queue: asyncio.Queue = asyncio.Queue(maxsize=GITHUB_QUEUE_MAXSIZE)
_worker_tasks: list[asyncio.Task] = []
_gh_repo_cache = StateCache(max_capacity=2000, default_ttl=3600.0)


def _gh_callback_data(full_name: str) -> str:
    direct = f"ghdl_{full_name}"
    if len(direct.encode("utf-8")) <= 64:
        return direct
    token = uuid.uuid4().hex[:12]
    _gh_repo_cache[token] = full_name
    return f"ghdl_tok_{token}"


async def download_worker():
    """ورکری که درخواست‌های درون صف را پردازش می‌کند"""
    while True:
        func, args = await download_queue.get()
        try:
            await func(*args)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Queue Worker Error: {e}")
        finally:
            download_queue.task_done()


async def stop_github_workers() -> None:
    for task in _worker_tasks:
        if not task.done():
            task.cancel()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()


async def enqueue_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id, repo_path, user_id
):
    """اضافه کردن درخواست به صف"""
    if not _worker_tasks:
        for _ in range(GITHUB_WORKERS):
            _worker_tasks.append(asyncio.create_task(download_worker()))

    if download_queue.full():
        await context.bot.send_message(
            chat_id,
            "🔴 صف دانلود گیت‌هاب در حال حاضر پر است. لطفاً چند لحظه دیگر تلاش کنید.",
        )
        return

    position = download_queue.qsize()
    await context.bot.send_message(
        chat_id, f"⏳ درخواست شما در صف قرار گرفت. (نفرات قبل از شما: $ {position} $)"
    )

    try:
        download_queue.put_nowait(
            (process_github_download, (update, context, chat_id, repo_path, user_id))
        )
    except asyncio.QueueFull:
        await context.bot.send_message(
            chat_id,
            "🔴 صف دانلود گیت‌هاب در حال حاضر پر است. لطفاً چند لحظه دیگر تلاش کنید.",
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

    user_id = str(update.effective_user.id)
    vip_status, downloads_count = await asyncio.gather(
        is_vip(user_id),
        get_gh_downloads(user_id),
    )
    max_dl = get_limit("github_download", vip_status)

    if downloads_count >= max_dl:
        await update.message.reply_text(
            "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
        )
        clear_state(chat_id)
        return

    if step == "waiting_gh_dl":
        repo_path = text.replace("https://github.com/", "").strip()
        # به جای پردازش مستقیم، به صف اضافه می‌کنیم
        await enqueue_download(update, context, chat_id, repo_path, user_id)

    elif step == "waiting_gh_user":
        await update.message.reply_text("⏳ در حال دریافت اطلاعات کاربر...")
        session = await get_http_session()
        encoded_user = quote(text.strip().lstrip("@"), safe="")
        async with session.get(
            f"https://api.github.com/users/{encoded_user}/repos?sort=updated&per_page=10",
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
                                callback_data=_gh_callback_data(repo["full_name"]),
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
            f"https://api.github.com/search/repositories?q={quote(text.strip(), safe='')}&per_page=10",
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
                                callback_data=_gh_callback_data(repo["full_name"]),
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

    await asyncio.to_thread(os.makedirs, GITHUB_TEMP_DIR, exist_ok=True)
    file_name = f"{repo_path.replace('/', '_')}.zip"
    temp_path = os.path.join(GITHUB_TEMP_DIR, f"temp_{uuid.uuid4().hex}_{file_name}")

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
                max_bytes = 50 * 1024 * 1024  # محدودیت 50 مگابایت
                try:
                    downloaded_size = await stream_aiohttp_to_file(
                        resp, temp_path, chunk_size=1024 * 1024, max_bytes=max_bytes
                    )
                except FileTooLargeError:
                    await context.bot.send_message(
                        chat_id,
                        "❌ بله پشتیبانی نمیشه (حجم فایل بالای ۵۰ مگابایت است).",
                    )
                    return

                file_size_mb = downloaded_size / (1024 * 1024)
                if file_size_mb < 0.001:
                    await context.bot.send_message(
                        chat_id,
                        "❌ فایل دریافتی نامعتبر است (احتمالاً ریپازیتوری وجود ندارد یا پرایوت است).",
                    )
                else:
                    doc_input = await load_input_file(temp_path, filename=file_name)
                    await context.bot.send_document(
                        chat_id=chat_id, document=doc_input, filename=file_name
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
        await remove_file_async(temp_path)
        clear_state(str(chat_id))


async def github_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = str(query.message.chat_id)
    user_id = str(query.from_user.id)

    if data.startswith("ghdl_"):
        raw_target = data.split("ghdl_", 1)[1]
        if raw_target.startswith("tok_"):
            repo_path = _gh_repo_cache.get(raw_target[4:])
            if not repo_path:
                await query.message.reply_text("❌ نشست منقضی شده است. لطفاً دوباره جستجو کنید.")
                return
        else:
            repo_path = raw_target

        vip_status, downloads_count = await asyncio.gather(
            is_vip(user_id),
            get_gh_downloads(user_id),
        )
        max_dl = get_limit("github_download", vip_status)

        if downloads_count >= max_dl:
            await query.message.reply_text(
                "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
            )
            return

        # به جای پردازش مستقیم، به صف اضافه می‌کنیم
        await enqueue_download(update, context, chat_id, repo_path, user_id)
