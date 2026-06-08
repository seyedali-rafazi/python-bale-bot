# main.py

import asyncio
import logging
import os
import time

from dotenv import load_dotenv

from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
)

from handlers import register_all_handlers

from core.database import init_db

from services.http_client import (
    init_http_session,
    close_http_session,
)

from services.pinterest_queue import (
    start_pinterest_workers,
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
# CLEANUP
# =========================================================


async def cleanup_old_downloads(
    context: ContextTypes.DEFAULT_TYPE,
):

    now = time.time()

    directories = [
        "downloads",
        "ig_downloads",
    ]

    for directory in directories:
        if not os.path.exists(directory):
            continue

        for f in os.listdir(directory):
            file_path = os.path.join(
                directory,
                f,
            )

            if not os.path.isfile(file_path):
                continue

            try:
                if os.stat(file_path).st_mtime < now - 7200:
                    os.remove(file_path)

                    logger.info(f"🗑️ deleted: {file_path}")

            except Exception:
                logger.exception("cleanup failed")


# =========================================================
# STARTUP
# =========================================================


async def on_startup(app):

    global _chromium_maintenance_task

    # 🔥 راهکار امن: با گرفتن آخرین آپدیت موجود، صف پیام‌های گذشته روی سرور بله کاملاً کور و پاک می‌شود
    try:
        updates = await app.bot.get_updates(offset=-1, timeout=1)
        if updates:
            # دادن آفست بالاتر به سرور اعلام می‌کند که تمام پیام‌های قبل از این ID پردازش شده تلقی شوند
            await app.bot.get_updates(offset=updates[-1].update_id + 1, timeout=1)
        logger.info("🗑️ Pending updates successfully cleared via safe offset approach")
    except Exception:
        logger.exception("Failed to flush pending updates smoothly")

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

    if _chromium_maintenance_task is not None and not _chromium_maintenance_task.done():
        _chromium_maintenance_task.cancel()
        try:
            await _chromium_maintenance_task
        except asyncio.CancelledError:
            pass

    try:
        await close_http_session()
        logger.info("✅ HTTP session closed on shutdown")
    except Exception:
        logger.exception("HTTP session cleanup on shutdown failed")

    try:
        await close_ai_client()
        logger.info("✅ AI client disconnected on shutdown")
    except Exception:
        logger.exception("AI client cleanup on shutdown failed")

    try:
        await get_browser_manager().cleanup()
        logger.info("✅ Playwright browser cleaned up on shutdown")
    except Exception:
        logger.exception("Playwright cleanup on shutdown failed")


# =========================================================
# MAIN
# =========================================================


def main():

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

    register_all_handlers(application)

    logger.info("✅ Bot Started")

    PORT = int(
        os.getenv(
            "PORT",
            BALE_LISTENING_PORT,
        )
    )

    polling_allowed_updates = [
        "message",
        "edited_message",
        "callback_query",
        "pre_checkout_query",
        "shipping_query",
    ]

    # پارامتر drop_pending_updates اینجا هم به درستی وظیفه‌اش را انجام خواهد داد
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=polling_allowed_updates,
    )


if __name__ == "__main__":
    main()
