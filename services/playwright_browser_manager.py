# services/playwright_browser_manager.py
"""
Singleton browser manager for Playwright (Async API).
Reuses a single browser instance across multiple searches.
"""

import asyncio
import time
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright


class PlaywrightBrowserManager:
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright: Optional[Playwright] = None
        self._last_context_time = time.time()
        self._context_timeout = 300
        self._init_lock = asyncio.Lock()  # تغییر به Lock ناهمگام

        self._usage_count = 0
        self._max_usages_before_restart = 100

    def _is_browser_alive(self) -> bool:
        try:
            if self._browser and self._browser.is_connected():
                return True
            return False
        except:
            return False

    async def _restart_browser(self):
        print("🔄 Restarting Playwright Browser...")
        await self.cleanup()
        self._browser = None
        self._playwright = None

    async def force_restart(self):
        async with self._init_lock:
            self._usage_count = 0
            await self._restart_browser()

    async def _initialize(self):
        async with self._init_lock:
            if self._browser is not None:
                if not self._is_browser_alive():
                    print("⚠️ Browser crashed, restarting...")
                    await self._restart_browser()

                elif self._usage_count >= self._max_usages_before_restart:
                    print(
                        f"♻️ Browser reached {self._usage_count} uses. Force restarting to free RAM..."
                    )
                    await self._restart_browser()

                else:
                    time_since_use = time.time() - self._last_context_time
                    if time_since_use > self._context_timeout:
                        print(
                            f"⚠️ Browser idle for {time_since_use:.0f}s, restarting..."
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
                        ],
                        timeout=30000,
                    )
                    self._usage_count = 0
                    self._last_context_time = time.time()
                    print("✅ Browser initialized")
                except Exception as e:
                    print(f"❌ Browser launch failed: {e}")
                    self._browser = None
                    if self._playwright:
                        await self._playwright.stop()
                    self._playwright = None
                    raise

    async def get_browser(self) -> Browser:
        await self._initialize()
        if self._browser is None:
            await self._initialize()
            if self._browser is None:
                raise Exception("Failed to initialize browser")
        return self._browser

    async def new_context(self, user_agent: str) -> BrowserContext:
        max_retries = 2

        for attempt in range(max_retries):
            try:
                browser = await self.get_browser()
                context = await browser.new_context(
                    user_agent=user_agent,
                    locale="en-US",
                    viewport={"width": 1400, "height": 2200},
                    device_scale_factor=1,
                )

                self._last_context_time = time.time()
                self._usage_count += 1

                return context

            except Exception as e:
                print(
                    f"❌ Context creation failed (Attempt {attempt + 1}/{max_retries}): {e}"
                )
                await self._restart_browser()
                if attempt == max_retries - 1:
                    raise e

    async def cleanup(self):
        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            print(f"Error closing browser: {e}")

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            print(f"Error closing playwright: {e}")


_browser_manager: Optional[PlaywrightBrowserManager] = None


def get_browser_manager() -> PlaywrightBrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = PlaywrightBrowserManager()
    return _browser_manager
