import asyncio
import hashlib
import re
from urllib.parse import quote
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from services.cache_service import cache_get, cache_set
from services.http_client import get_http_session
from services.rate_limiter import user_action_lock
from telegram.ext import ContextTypes
from core.database import get_gh_downloads, increment_gh_downloads, is_vip
from core.limits import get_limit
from core.state_manager import StateCache, clear_state
from handlers.utils import safe_answer_query
from core.task_utils import (
    FileTooLargeError,
    bounded_large_upload,
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
_inflight_gh_queries: dict[str, asyncio.Task] = {}
_pending_gh_downloads: dict[str, int] = {}
_GH_API_CACHE_TTL_SEC = 300


async def _fetch_github_json_cached(cache_key: str, url: str) -> tuple[int, object]:
    cached = await cache_get(cache_key)
    if isinstance(cached, dict) and "status" in cached and "data" in cached:
        return int(cached["status"]), cached["data"]

    existing = _inflight_gh_queries.get(cache_key)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    async def _fetch() -> tuple[int, object]:
        session = await get_http_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            status = resp.status
            data = await resp.json() if status == 200 else None
        if status == 200 and data is not None:
            await cache_set(cache_key, {"status": status, "data": data}, ttl_sec=_GH_API_CACHE_TTL_SEC)
        return status, data

    task = asyncio.create_task(_fetch())
    _inflight_gh_queries[cache_key] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _inflight_gh_queries.get(cache_key) is done_task:
            _inflight_gh_queries.pop(cache_key, None)
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)


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


def _normalize_github_repo(raw: str) -> str | None:
    s = (raw or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+/[^/\s?#]+)", s, re.IGNORECASE)
    repo = m.group(1) if m else s
    repo = repo.strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    parts = [p for p in repo.split("/") if p]
    if len(parts) < 2:
        return None
    owner, name = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", owner) or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return None
    return f"{owner}/{name}"


async def enqueue_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id, repo_path, user_id
):
    """اضافه کردن درخواست به صف"""
    _worker_tasks[:] = [t for t in _worker_tasks if not t.done()]
    while len(_worker_tasks) < GITHUB_WORKERS:
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
            (process_github_download, (context, chat_id, repo_path, user_id))
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

    if step == "waiting_gh_dl":
        repo_path = _normalize_github_repo(text)
        if not repo_path:
            await update.message.reply_text(
                "❌ فرمت ریپازیتوری نامعتبر است. مثال:\n`owner/repo` یا `https://github.com/owner/repo`"
            )
            return

        async with user_action_lock(user_id, "gh_dl", timeout_sec=10) as acquired:
            if not acquired:
                await update.message.reply_text("⏳ درخواست قبلی شما در حال ثبت است. لطفاً صبر کنید.")
                return
            vip_status, downloads_count = await asyncio.gather(
                is_vip(user_id),
                get_gh_downloads(user_id),
            )
            max_dl = get_limit("github_download", vip_status)
            pending = _pending_gh_downloads.get(user_id, 0)

            if downloads_count + pending >= max_dl:
                await update.message.reply_text(
                    "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
                )
                clear_state(chat_id)
                return

            _pending_gh_downloads[user_id] = pending + 1
            clear_state(chat_id)
            try:
                await enqueue_download(update, context, chat_id, repo_path, user_id)
            except BaseException:
                cur = _pending_gh_downloads.get(user_id, 0)
                if cur <= 1:
                    _pending_gh_downloads.pop(user_id, None)
                else:
                    _pending_gh_downloads[user_id] = cur - 1
                raise

    elif step == "waiting_gh_user":
        async with user_action_lock(user_id, "gh_search", timeout_sec=15) as acquired:
            if not acquired:
                await update.message.reply_text("⏳ درخواست قبلی شما در حال انجام است. لطفاً صبر کنید.")
                return
            await update.message.reply_text("⏳ در حال دریافت اطلاعات کاربر...")
            clean_user = text.strip().lstrip("@")
            encoded_user = quote(clean_user, safe="")
            u_hash = hashlib.md5(clean_user.lower().encode("utf-8")).hexdigest()[:16]
            try:
                status, repos = await _fetch_github_json_cached(
                    f"gh:user:{u_hash}",
                    f"https://api.github.com/users/{encoded_user}/repos?sort=updated&per_page=10",
                )
                if status == 200 and isinstance(repos, list):
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
            except Exception:
                await update.message.reply_text("❌ خطا در ارتباط با گیت‌هاب. لطفاً دوباره تلاش کنید.")

    elif step == "waiting_gh_search":
        async with user_action_lock(user_id, "gh_search", timeout_sec=15) as acquired:
            if not acquired:
                await update.message.reply_text("⏳ جستجوی قبلی شما در حال انجام است. لطفاً صبر کنید.")
                return
            await update.message.reply_text("⏳ در حال جستجو در گیت‌هاب...")
            clean_query = text.strip()
            q_hash = hashlib.md5(clean_query.lower().encode("utf-8")).hexdigest()[:16]
            try:
                status, data = await _fetch_github_json_cached(
                    f"gh:search:{q_hash}",
                    f"https://api.github.com/search/repositories?q={quote(clean_query, safe='')}&per_page=10",
                )
                if status == 200 and isinstance(data, dict):
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
            except Exception:
                await update.message.reply_text("❌ خطا در ارتباط با گیت‌هاب. لطفاً دوباره تلاش کنید.")


async def process_github_download(
    context: ContextTypes.DEFAULT_TYPE, chat_id, repo_path, user_id
):
    vip_status, downloads_count = await asyncio.gather(
        is_vip(user_id),
        get_gh_downloads(user_id),
    )
    if downloads_count >= get_limit("github_download", vip_status):
        await context.bot.send_message(
            chat_id, "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
        )
        return

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

        async def _send_preview_safe():
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

        preview_task = track_task(_send_preview_safe(), name=f"gh_preview_{chat_id}")

        async with session.get(
            zip_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=120)
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
                    async with bounded_large_upload():
                        doc_input = await load_input_file(temp_path, filename=file_name)
                        try:
                            await context.bot.send_document(
                                chat_id=chat_id, document=doc_input, filename=file_name
                            )
                        finally:
                            del doc_input
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
        uid = str(user_id)
        cur = _pending_gh_downloads.get(uid, 0)
        if cur <= 1:
            _pending_gh_downloads.pop(uid, None)
        else:
            _pending_gh_downloads[uid] = cur - 1


async def github_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    data = query.data or ""
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

        async with user_action_lock(user_id, "gh_dl", timeout_sec=10) as acquired:
            if not acquired:
                await query.message.reply_text("⏳ درخواست قبلی شما در حال ثبت است. لطفاً صبر کنید.")
                return

            vip_status, downloads_count = await asyncio.gather(
                is_vip(user_id),
                get_gh_downloads(user_id),
            )
            max_dl = get_limit("github_download", vip_status)
            pending = _pending_gh_downloads.get(user_id, 0)

            if downloads_count + pending >= max_dl:
                await query.message.reply_text(
                    "❌ محدودیت دانلود روزانه شما به اتمام رسیده است."
                )
                return

            _pending_gh_downloads[user_id] = pending + 1
            clear_state(chat_id)
            try:
                await enqueue_download(update, context, chat_id, repo_path, user_id)
            except BaseException:
                cur = _pending_gh_downloads.get(user_id, 0)
                if cur <= 1:
                    _pending_gh_downloads.pop(user_id, None)
                else:
                    _pending_gh_downloads[user_id] = cur - 1
                raise
