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
import json


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

    # #region agent log (debug-80597c)
    _DBG_LOG_PATH = "debug-80597c.log"
    _DBG_SESSION_ID = "80597c"
    _dbg_lock = threading.Lock()

    def _dbg_log(self, hypothesisId: str, location: str, message: str, data: dict, runId: str = "pre-fix"):
        payload = {
            "sessionId": self._DBG_SESSION_ID,
            "runId": runId,
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        try:
            line = json.dumps(payload, ensure_ascii=False)
            with self._dbg_lock:
                with open(self._DBG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            pass

    # #endregion agent log (debug-80597c)

    def _is_browser_alive(self) -> bool:
        try:
            if self._browser and self._browser.is_connected():
                return True
            return False
        except:
            return False

    def _restart_browser(self):
        print("🔄 Restarting Playwright Browser...")
        self._dbg_log(
            hypothesisId="B",
            location="services/playwright_browser_manager.py:_restart_browser",
            message="Restarting browser",
            data={"usageCount": self._usage_count},
        )
        self.cleanup()
        self._browser = None
        self._playwright = None

    def _initialize(self):
        with self._init_lock:
            if self._browser is not None:
                # بررسی زنده بودن مرورگر
                if not self._is_browser_alive():
                    print("⚠️ Browser crashed, restarting...")
                    self._dbg_log(
                        hypothesisId="B",
                        location="services/playwright_browser_manager.py:_initialize",
                        message="Browser not alive; restarting",
                        data={"usageCount": self._usage_count},
                    )
                    self._restart_browser()
                    return

                # بررسی تعداد دفعات استفاده برای جلوگیری از پر شدن رم
                if self._usage_count >= self._max_usages_before_restart:
                    print(
                        f"♻️ Browser reached {self._usage_count} uses. Force restarting to free RAM..."
                    )
                    self._dbg_log(
                        hypothesisId="B",
                        location="services/playwright_browser_manager.py:_initialize",
                        message="Max usages reached; restarting",
                        data={
                            "usageCount": self._usage_count,
                            "maxBeforeRestart": self._max_usages_before_restart,
                        },
                    )
                    self._restart_browser()
                    return

                # بررسی تایم‌اوت در صورت بیکاری مرورگر
                time_since_use = time.time() - self._last_context_time
                if time_since_use > self._context_timeout:
                    print(f"⚠️ Browser idle for {time_since_use:.0f}s, restarting...")
                    self._dbg_log(
                        hypothesisId="B",
                        location="services/playwright_browser_manager.py:_initialize",
                        message="Idle timeout; restarting",
                        data={"idleSeconds": int(time_since_use), "contextTimeout": self._context_timeout},
                    )
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
                    self._dbg_log(
                        hypothesisId="B",
                        location="services/playwright_browser_manager.py:_initialize",
                        message="Browser initialized",
                        data={"headless": True},
                    )
                except Exception as e:
                    print(f"❌ Browser launch failed: {e}")
                    self._dbg_log(
                        hypothesisId="B",
                        location="services/playwright_browser_manager.py:_initialize",
                        message="Browser launch failed",
                        data={"errType": e.__class__.__name__},
                    )
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
                self._dbg_log(
                    hypothesisId="B",
                    location="services/playwright_browser_manager.py:new_context",
                    message="Creating context",
                    data={"attempt": attempt + 1, "usageCount": self._usage_count, "thread": threading.current_thread().name},
                )
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
                self._dbg_log(
                    hypothesisId="B",
                    location="services/playwright_browser_manager.py:new_context",
                    message="Context creation failed",
                    data={"attempt": attempt + 1, "errType": e.__class__.__name__},
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
