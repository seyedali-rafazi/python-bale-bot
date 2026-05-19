# services/playwright_browser_manager.py
"""
Singleton browser manager for Playwright (Sync API).
Reuses a single browser instance across multiple searches within the same process.
Works with ProcessPoolExecutor with proper error handling and timeouts.

CRITICAL: Must be used in a separate process/thread, NOT in asyncio loop!
"""

from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext
import atexit
import time
import threading


class PlaywrightBrowserManager:
    def __init__(self):
        self._browser: Browser | None = None
        self._playwright = None
        self._last_context_time = time.time()
        self._context_timeout = 300
        self._init_lock = threading.Lock()

        # متغیرهای مربوط به ری‌استارت اجباری برای جلوگیری از نشت حافظه (Memory Leak)
        self._usage_count = 0
        self._max_usages_before_restart = 100  # بعد از ۱۰۰ بار استفاده ریستارت شود

        atexit.register(self.cleanup)

    def _is_browser_alive(self) -> bool:
        try:
            if self._browser and self._browser.is_connected():
                return True
            return False
        except:
            return False

    def _restart_browser(self):
        print("🔄 Restarting Playwright Browser...")
        self.cleanup()
        self._browser = None
        self._playwright = None

    def _initialize(self):
        with self._init_lock:
            if self._browser is not None:
                # بررسی زنده بودن مرورگر
                if not self._is_browser_alive():
                    print("⚠️ Browser crashed, restarting...")
                    self._restart_browser()
                    return

                # بررسی تعداد دفعات استفاده برای جلوگیری از پر شدن رم
                if self._usage_count >= self._max_usages_before_restart:
                    print(
                        f"♻️ Browser reached {self._usage_count} uses. Force restarting to free RAM..."
                    )
                    self._restart_browser()
                    return

                # بررسی تایم‌اوت در صورت بیکاری مرورگر
                time_since_use = time.time() - self._last_context_time
                if time_since_use > self._context_timeout:
                    print(f"⚠️ Browser idle for {time_since_use:.0f}s, restarting...")
                    self._restart_browser()
                    return

                return

            if self._browser is None:
                try:
                    self._playwright = sync_playwright().__enter__()
                    self._browser = self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-web-resources",
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
                    self._usage_count = 0  # صفر کردن شمارنده بعد از ساخت مرورگر جدید
                    self._last_context_time = time.time()
                    print("✅ Browser initialized")
                except Exception as e:
                    print(f"❌ Browser launch failed: {e}")
                    self._browser = None
                    self._playwright = None
                    raise

    def get_browser(self) -> Browser:
        self._initialize()
        if self._browser is None:
            self._initialize()  # تلاش مجدد در صورت خطا
            if self._browser is None:
                raise Exception("Failed to initialize browser")
        return self._browser

    def new_context(self, user_agent: str) -> BrowserContext:
        max_retries = 2

        for attempt in range(max_retries):
            try:
                browser = self.get_browser()
                context = browser.new_context(
                    user_agent=user_agent,
                    locale="en-US",
                    viewport={"width": 1400, "height": 2200},
                    device_scale_factor=1,
                )

                self._last_context_time = time.time()
                self._usage_count += 1  # افزایش شمارنده استفاده

                return context

            except Exception as e:
                print(
                    f"❌ Context creation failed (Attempt {attempt + 1}/{max_retries}): {e}"
                )
                self._restart_browser()
                if attempt == max_retries - 1:
                    raise e

    def cleanup(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception as e:
            print(f"Error closing browser: {e}")

        try:
            if self._playwright:
                self._playwright.__exit__(None, None, None)
        except Exception as e:
            print(f"Error closing playwright: {e}")


# Global singleton instance per process
_browser_manager: Optional[PlaywrightBrowserManager] = None


def get_browser_manager() -> PlaywrightBrowserManager:
    """Get the global browser manager instance (one per process)."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = PlaywrightBrowserManager()
    return _browser_manager
