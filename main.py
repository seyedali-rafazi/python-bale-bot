# main.py

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
)

from services.pinterest_queue import (
    start_pinterest_workers,
)

from services.ai import (
    init_ai_client,
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

    await init_http_session()

    await init_db()

    await start_pinterest_workers()

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
    logger.info("✅ AI Client initialized")


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
        .build()
    )

    if application.job_queue:
        application.job_queue.run_repeating(
            cleanup_old_downloads,
            interval=7200,
            first=30,
        )

    register_all_handlers(application)

    logger.info("✅ Bot Started")

    PORT = int(
        os.getenv(
            "PORT",
            BALE_LISTENING_PORT,
        )
    )

    WEBHOOK_URL = f"{BALE_URL}/{BALE_TOKEN}"

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BALE_TOKEN,
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=None,
    )


if __name__ == "__main__":
    main()
