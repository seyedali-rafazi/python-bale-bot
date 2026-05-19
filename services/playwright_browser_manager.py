# services/playwright_browser_manager.py
"""
Singleton browser manager for Playwright (Sync API).
Reuses a single browser instance across multiple searches within the same process.
Works with ProcessPoolExecutor with proper error handling and timeouts.

CRITICAL: Must be used in a separate process/thread, NOT in asyncio loop!
"""

from typing import Optional
from playwright.sync_api import Browser, BrowserContext
import atexit
import time
import threading

class PlaywrightBrowserManager:
    """Manages a single persistent browser instance for all searches in a process."""
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright = None
        self._last_context_time = time.time()
        self._context_timeout = 300  # 5 minutes between contexts = browser health check
        self._init_lock = threading.Lock()  # Thread-safe initialization
        # Register cleanup on process exit
        atexit.register(self.cleanup)
    
    def _is_browser_alive(self) -> bool:
        """Check if browser is still running."""
        if self._browser is None:
            return False
        try:
            # Quick health check - get version to verify browser responds
            self._browser.browser_type.name
            return True
        except Exception as e:
            print(f"⚠️ Browser health check failed: {e}")
            return False
    
    def _initialize(self):
        """Initialize Playwright and browser."""
        # Prevent race conditions with thread lock
        with self._init_lock:
            # Double-check pattern
            if self._browser is not None:
                if not self._is_browser_alive():
                    print("⚠️ Browser crashed, restarting...")
                    self._restart_browser()
                    return
                
                # Restart browser if it's been too long without activity (stale)
                time_since_use = time.time() - self._last_context_time
                if time_since_use > self._context_timeout:
                    print(f"⚠️ Browser idle for {time_since_use:.0f}s, restarting for safety...")
                    self._restart_browser()
                    return
                
                return  # Browser already initialized and healthy
            
            # Initialize fresh browser
            if self._browser is None:
                from playwright.sync_api import sync_playwright
                
                try:
                    # Initialize Playwright
                    self._playwright = sync_playwright().__enter__()
                    
                    # Memory-optimized launch arguments (NO --single-process!)
                    self._browser = self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",  # Disable GPU to save memory
                            "--disable-web-resources",
                            "--disable-extensions",
                            "--disable-component-extensions-with-background-pages",
                            "--disable-default-apps",
                            "--disable-features=TranslateUI",
                            "--disable-sync",
                            "--disable-translate",
                            "--mute-audio",
                        ],
                        timeout=30000,  # 30 second launch timeout
                    )
                    print("✅ Browser initialized (singleton per process)")
                except Exception as e:
                    print(f"❌ Browser launch failed: {e}")
                    self._browser = None
                    self._playwright = None
                    raise
    
    def _restart_browser(self):
        """Close old browser and start fresh."""
        try:
            if self._browser:
                self._browser.close()
                print("✅ Old browser closed")
        except Exception as e:
            print(f"⚠️ Error closing old browser: {e}")
        
        self._browser = None
        if self._playwright:
            try:
                self._playwright.__exit__(None, None, None)
                print("✅ Playwright closed")
            except:
                pass
        self._playwright = None
        
        # Initialize new browser
        self._initialize()
    
    def get_browser(self) -> Browser:
        """Get the browser instance, creating or restarting as needed."""
        self._initialize()
        return self._browser
    
    def new_context(self, user_agent: str) -> BrowserContext:
        """Create a new context (tab) in the shared browser."""
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
                return context
            
            except Exception as e:
                print(f"❌ Failed to create context (attempt {attempt + 1}): {e}")
                
                # If this is the last attempt, raise
                if attempt >= max_retries - 1:
                    raise
                
                # Otherwise, restart browser and retry
                print(f"Restarting browser and retrying...")
                with self._init_lock:
                    self._restart_browser()
    
    def cleanup(self):
        """Close the browser."""
        with self._init_lock:
            if self._browser:
                try:
                    self._browser.close()
                    print("✅ Browser closed gracefully")
                except Exception as e:
                    print(f"⚠️ Error closing browser: {e}")
                finally:
                    self._browser = None
                    if self._playwright:
                        try:
                            self._playwright.__exit__(None, None, None)
                        except:
                            pass
                        self._playwright = None


# Global singleton instance per process
_browser_manager: Optional[PlaywrightBrowserManager] = None


def get_browser_manager() -> PlaywrightBrowserManager:
    """Get the global browser manager instance (one per process)."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = PlaywrightBrowserManager()
    return _browser_manager
