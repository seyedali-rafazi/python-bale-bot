import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
)

from core.database import init_db, close_db
from core.admin import stop_broadcast

from services.http_client import (
    init_http_session,
    close_http_session,
)

from services.pinterest_queue import (
    start_pinterest_workers,
    stop_pinterest_workers,
)
from services.playwright_browser_manager import get_browser_manager
from services.chromium_maintenance import chromium_maintenance_loop
from services.hourly_monitoring import (
    send_hourly_monitoring_report,
    seconds_until_next_hour_tehran,
)

from services.ai import (
    init_ai_client,
    close_ai_client,
)
from services.redis_client import (
    init_redis,
    close_redis,
)
from services.rate_limiter import check_anti_flood

load_dotenv()

BALE_TOKEN = os.getenv("BALE_TOKEN")

BALE_URL = os.getenv("BALE_URL")

BALE_LISTENING_PORT = os.getenv("BALE_LISTENING_PORT")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

_chromium_maintenance_task: asyncio.Task | None = None


# =========================================================
# ANTI-SPAM FILTER (نسخه پیشرفته ۳ لایه با محافظت فلود)
# =========================================================

BOT_START_TIME_UTC = datetime.now(timezone.utc)
PROCESS_START_TIME = time.time()

async def ignore_old_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    فیلتر پیشرفته برای جلوگیری از اجرای پیام‌ها و کلیک‌های قدیمی بله و محافظت در برابر اسپم
    """
    uptime = time.time() - PROCESS_START_TIME

    # لایه ۱: گارد استارت‌آپ (Blackhole)
    # در ۱۵ ثانیه اول راه‌اندازی ربات، برای تخلیه صف سرور بله، تمام آپدیت‌ها مستقیماً دور ریخته می‌شوند
    if uptime < 15:
        raise ApplicationHandlerStop()

    # لایه ۲: بررسی دقیق تاریخ برای تمام انواع پیام‌ها
    # این بار کلیک روی دکمه‌ها و پیام‌های کانال را هم بررسی می‌کنیم
    msg_date = None
    if update.message:
        msg_date = update.message.date
    elif update.edited_message:
        msg_date = update.edited_message.date
    elif update.callback_query and update.callback_query.message:
        msg_date = update.callback_query.message.date
    elif update.channel_post:
        msg_date = update.channel_post.date
    elif update.edited_channel_post:
        msg_date = update.edited_channel_post.date

    # اگر تاریخ پیام متعلق به قبل از لحظه استارت ربات باشد، پردازش متوقف می‌شود
    if msg_date and msg_date < BOT_START_TIME_UTC:
        raise ApplicationHandlerStop()

    # لایه ۳: ضداسپم و محافظت آنتی‌فلود ردیس (حداکثر ۱۰ درخواست در ۳ ثانیه)
    user = update.effective_user
    if user and not user.is_bot:
        if not await check_anti_flood(user.id, max_messages=10, window_sec=3):
            logger.warning("🚫 Anti-flood triggered for user %s, dropping update.", user.id)
            raise ApplicationHandlerStop()


# =========================================================
# CLEANUP
# =========================================================

DOWNLOAD_CLEANUP_DIRS = [
    "downloads",
    "ig_downloads",
]


async def cleanup_old_downloads(
    context: ContextTypes.DEFAULT_TYPE = None,
    directories: list[str] | None = None,
):
    now = time.time()
    max_age_sec = 7200  # 2 hours

    target_dirs = directories or DOWNLOAD_CLEANUP_DIRS

    total_scanned = 0
    total_deleted = 0
    total_errors = 0

    for directory in target_dirs:
        if not os.path.exists(directory):
            continue

        try:
            base_real = os.path.realpath(directory)
        except Exception as e:
            logger.warning("Could not resolve base path %s: %s", directory, e)
            continue

        for root, _dirs, files in os.walk(directory):
            for f in files:
                file_path = os.path.join(root, f)
                total_scanned += 1

                try:
                    # Guard against symlink path traversal outside allowed root
                    file_real = os.path.realpath(file_path)
                    if not (file_real == base_real or file_real.startswith(base_real + os.sep)):
                        logger.warning("Skipping file outside allowed directory root: %s", file_path)
                        continue

                    # Protect newly created or active downloads
                    st = os.stat(file_path, follow_symlinks=False)
                    if st.st_mtime < now - max_age_sec:
                        os.remove(file_path)
                        total_deleted += 1
                except FileNotFoundError:
                    # Concurrently removed by another process or handler
                    pass
                except PermissionError:
                    total_errors += 1
                    logger.debug("Permission error when removing expired file: %s", file_path)
                except Exception as e:
                    total_errors += 1
                    logger.debug("Failed to remove file %s: %s", file_path, e)

    logger.info(
        "🧹 Download cleanup finished: scanned=%d, deleted=%d, errors=%d",
        total_scanned,
        total_deleted,
        total_errors,
    )


# =========================================================
# STARTUP
# =========================================================

async def on_startup(app):
    global _chromium_maintenance_task

    await init_redis()

    await init_http_session()

    await init_db()

    await start_pinterest_workers()

    _chromium_maintenance_task = asyncio.create_task(chromium_maintenance_loop())

    await init_ai_client()

    from core.database.youtube import (
        drop_legacy_user_youtube_archive_table,
        purge_incomplete_youtube_cache,
    )

    await drop_legacy_user_youtube_archive_table()
    removed = await purge_incomplete_youtube_cache()
    if removed > 0:
        logger.info("YT cache: removed %s incomplete/ناشناس rows", removed)

    logger.info("✅ HTTP Session initialized")
    logger.info("✅ Database initialized")
    logger.info("✅ Pinterest workers initialized")
    logger.info("✅ Chromium periodic maintenance started")
    logger.info("✅ AI Client initialized")


async def on_shutdown(app):
    global _chromium_maintenance_task

    # 1. Stop background maintenance loop
    if _chromium_maintenance_task is not None and not _chromium_maintenance_task.done():
        _chromium_maintenance_task.cancel()
        try:
            await _chromium_maintenance_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error cancelling chromium maintenance task on shutdown")

    # 2. Stop running broadcast tasks
    try:
        await stop_broadcast()
    except Exception:
        logger.exception("Error stopping broadcast task on shutdown")

    # 3. Stop Pinterest queue worker tasks
    try:
        await stop_pinterest_workers()
        logger.info("✅ Pinterest workers stopped on shutdown")
    except Exception:
        logger.exception("Error stopping Pinterest workers on shutdown")

    # 4. Clean up Playwright browser instances
    try:
        await get_browser_manager().cleanup()
        logger.info("✅ Playwright browser cleaned up on shutdown")
    except Exception:
        logger.exception("Playwright cleanup on shutdown failed")

    # 5. Close HTTP client sessions
    try:
        await close_http_session()
        logger.info("✅ HTTP session closed on shutdown")
    except Exception:
        logger.exception("HTTP session cleanup on shutdown failed")

    # 6. Disconnect AI client
    try:
        await close_ai_client()
        logger.info("✅ AI client disconnected on shutdown")
    except Exception:
        logger.exception("AI client cleanup on shutdown failed")

    # 7. Close SQLite database (after in-flight tasks and clients are done)
    try:
        await close_db()
    except Exception:
        logger.exception("SQLite close_db on shutdown failed")

    # 8. Close Redis client
    try:
        await close_redis()
    except Exception:
        logger.exception("Redis cleanup on shutdown failed")


# =========================================================
# MAIN
# =========================================================

def main():
    if not BALE_TOKEN:
        raise RuntimeError(
            "BALE_TOKEN is not set in the environment. Please set it in your .env file."
        )

    application = (
        ApplicationBuilder()
        .token(BALE_TOKEN)
        .base_url("https://tapi.bale.ai/bot")
        .base_file_url("https://tapi.bale.ai/file/bot")
        .concurrent_updates(True)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    if application.job_queue:
        application.job_queue.run_repeating(
            cleanup_old_downloads,
            interval=7200,
            first=30,
        )
        application.job_queue.run_repeating(
            send_hourly_monitoring_report,
            interval=3600,
            first=seconds_until_next_hour_tehran(),
            name="hourly_monitoring_report",
        )
        logger.info("✅ Hourly monitoring report scheduled")

    # +++ اعمال فیلتر زمانی قبل از سایر هندلرها در گروه ۱- +++
    application.add_handler(TypeHandler(Update, ignore_old_updates), group=-1)

    from handlers import register_all_handlers
    register_all_handlers(application)

    logger.info("✅ Bot Started")

    allowed_updates = [
        "message",
        "edited_message",
        "callback_query",
        "pre_checkout_query",
        "shipping_query",
    ]

    if BALE_URL and BALE_TOKEN:
        PORT = int(
            os.getenv(
                "PORT",
                BALE_LISTENING_PORT or "8443",
            )
        )

        WEBHOOK_URL = f"{BALE_URL}/{BALE_TOKEN}"

        try:
            logger.info("🌐 Attempting to start in WEBHOOK mode...")
            logger.info(f"   Webhook URL: {WEBHOOK_URL}")
            logger.info(f"   Listening on port: {PORT}")

            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=BALE_TOKEN,
                webhook_url=WEBHOOK_URL,
                drop_pending_updates=True,
                allowed_updates=allowed_updates,
            )
        except Exception as e:
            logger.error(f"❌ Webhook mode failed: {e}")
            logger.info("🔄 Falling back to POLLING mode...")

            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=allowed_updates,
            )
    else:
        logger.warning("⚠️  BALE_URL or BALE_TOKEN not set — running in POLLING mode")

        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=allowed_updates,
        )


if __name__ == "__main__":
    main()