# services/playwright_browser_manager.py
"""
Singleton browser manager for Playwright (Async API).
Reuses a single browser instance across multiple searches.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Any

logger = logging.getLogger(__name__)
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright
except ImportError:
    async_playwright = None
    Browser = Any  # type: ignore
    BrowserContext = Any  # type: ignore
    Playwright = Any  # type: ignore



class PlaywrightBrowserManager:
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright: Optional[Playwright] = None
        self._last_context_time = time.time()
        self._browser_started_at = 0.0
        self._context_timeout = max(60, int(os.getenv("CHROMIUM_IDLE_RESTART_SEC", "120")))
        self._init_lock = asyncio.Lock()

        self._usage_count = 0
        self._active_context_ids: set[int] = set()
        self._max_usages_before_restart = max(
            3, int(os.getenv("CHROMIUM_MAX_USES_BEFORE_RESTART", "8"))
        )
        self._max_browser_age_sec = max(
            300, int(os.getenv("CHROMIUM_MAX_BROWSER_AGE_SEC", "1800"))
        )
        self._idle_close_task: Optional[asyncio.Task] = None

    def _is_browser_alive(self) -> bool:
        try:
            if self._browser and self._browser.is_connected():
                return True
            return False
        except Exception:
            return False

    def is_idle(self) -> bool:
        return not self._active_context_ids and not self._is_browser_alive()

    def _schedule_idle_close(self) -> None:
        if self._idle_close_task is not None and not self._idle_close_task.done():
            self._idle_close_task.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _idle_watchdog():
            await asyncio.sleep(self._context_timeout + 5)
            async with self._init_lock:
                if (
                    self._browser is not None
                    and not self._active_context_ids
                    and (time.time() - self._last_context_time) >= self._context_timeout
                ):
                    logger.info("Browser idle watchdog closing Chromium to reclaim RAM...")
                    await self._cleanup_unlocked()

        self._idle_close_task = loop.create_task(_idle_watchdog())

    async def _restart_browser(self):
        logger.info("Restarting Playwright Browser...")
        await self._cleanup_unlocked()

    async def force_restart(self):
        async with self._init_lock:
            if self._active_context_ids and self._is_browser_alive():
                logger.warning(
                    "Skipping force_restart while %s context(s) active",
                    len(self._active_context_ids),
                )
                return
            self._usage_count = 0
            await self._restart_browser()

    async def _initialize_locked(self):
        if self._browser is not None:
            if not self._is_browser_alive():
                logger.warning("Browser crashed, restarting...")
                await self._restart_browser()

            elif self._active_context_ids:
                # Another concurrent worker holds an open context; defer recycle until idle
                pass

            elif self._usage_count >= self._max_usages_before_restart:
                logger.info(
                    "Browser reached %s uses. Force restarting to free RAM...",
                    self._usage_count,
                )
                await self._restart_browser()

            elif (
                self._browser_started_at > 0
                and time.time() - self._browser_started_at
                > self._max_browser_age_sec
            ):
                age = time.time() - self._browser_started_at
                logger.info(
                    "Browser age %.0fs exceeds %ss, restarting...",
                    age,
                    self._max_browser_age_sec,
                )
                await self._restart_browser()

            else:
                time_since_use = time.time() - self._last_context_time
                if time_since_use > self._context_timeout:
                    logger.info(
                        "Browser idle for %.0fs, restarting...",
                        time_since_use,
                    )
                    await self._restart_browser()

        if self._browser is None:
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-component-extensions-with-background-pages",
                        "--disable-default-apps",
                        "--disable-features=TranslateUI",
                        "--disable-sync",
                        "--disable-translate",
                        "--mute-audio",
                        "--renderer-process-limit=2",
                        "--disable-background-networking",
                        "--disable-background-timer-throttling",
                        "--disable-renderer-backgrounding",
                    ],
                    timeout=30000,
                )
                self._usage_count = 0
                self._last_context_time = time.time()
                self._browser_started_at = time.time()
                logger.info("Browser initialized")
            except Exception as e:
                logger.warning("Browser launch failed: %s", e)
                self._browser = None
                if self._playwright:
                    await self._playwright.stop()
                self._playwright = None
                raise

    async def _initialize(self):
        async with self._init_lock:
            await self._initialize_locked()

    async def get_browser(self) -> Browser:
        async with self._init_lock:
            await self._initialize_locked()
            if self._browser is None:
                raise RuntimeError("Failed to initialize browser")
            return self._browser

    async def new_context(self, user_agent: str) -> BrowserContext:
        max_retries = 2

        for attempt in range(max_retries):
            try:
                async with self._init_lock:
                    await self._initialize_locked()
                    if self._browser is None:
                        raise RuntimeError("Failed to initialize browser")
                    context = await self._browser.new_context(
                        user_agent=user_agent,
                        locale="en-US",
                        viewport={"width": 1280, "height": 1600},
                        device_scale_factor=1,
                    )

                    self._last_context_time = time.time()
                    self._usage_count += 1
                    ctx_id = id(context)
                    self._active_context_ids.add(ctx_id)

                orig_close = context.close

                async def _tracked_close():
                    try:
                        return await orig_close()
                    finally:
                        self._active_context_ids.discard(ctx_id)
                        self._last_context_time = time.time()
                        if not self._active_context_ids:
                            self._schedule_idle_close()

                context.close = _tracked_close
                return context

            except Exception as e:
                logger.warning(
                    "Context creation failed (Attempt %s/%s): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                async with self._init_lock:
                    if not self._active_context_ids or not self._is_browser_alive():
                        await self._restart_browser()
                if attempt == max_retries - 1:
                    raise e

    async def _cleanup_unlocked(self):
        if self._idle_close_task is not None and not self._idle_close_task.done():
            self._idle_close_task.cancel()
            self._idle_close_task = None

        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.debug("Error closing browser: %s", e)
        finally:
            self._browser = None

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug("Error closing playwright: %s", e)
        finally:
            self._playwright = None

        self._usage_count = 0
        self._browser_started_at = 0.0
        self._active_context_ids.clear()

    async def cleanup(self):
        async with self._init_lock:
            await self._cleanup_unlocked()


_browser_manager: Optional[PlaywrightBrowserManager] = None


def get_browser_manager() -> PlaywrightBrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = PlaywrightBrowserManager()
    return _browser_manager
