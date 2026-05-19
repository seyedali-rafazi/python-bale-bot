# services/playwright_browser_manager.py
"""
Singleton browser manager for Playwright.
Reuses a single browser instance across multiple searches within the same process.
Works with ProcessPoolExecutor.
"""

from typing import Optional
from playwright.sync_api import Browser, BrowserContext
import atexit

class PlaywrightBrowserManager:
    """Manages a single persistent browser instance for all searches in a process."""
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright = None
        # Register cleanup on process exit
        atexit.register(self.cleanup)
    
    def _initialize(self):
        """Initialize Playwright and browser."""
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            
            self._playwright = sync_playwright().__enter__()
            
            # Optimized for minimal memory usage
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
                    "--single-process",  # Single process = less RAM per worker
                    "--mute-audio",
                    "--disable-sync",
                    "--disable-translate",
                    "--disable-preconnect",
                ],
            )
            print("✅ Browser initialized (singleton per process)")
    
    def get_browser(self) -> Browser:
        """Get the browser instance."""
        self._initialize()
        return self._browser
    
    def new_context(self, user_agent: str) -> BrowserContext:
        """Create a new context (tab) in the shared browser."""
        browser = self.get_browser()
        
        context = browser.new_context(
            user_agent=user_agent,
            locale="en-US",
            viewport={"width": 1400, "height": 2200},
            device_scale_factor=1,
        )
        return context
    
    def cleanup(self):
        """Close the browser."""
        if self._browser:
            try:
                self._browser.close()
                print("✅ Browser closed")
            except Exception as e:
                print(f"Error closing browser: {e}")
            finally:
                self._browser = None
                if self._playwright:
                    self._playwright.__exit__(None, None, None)
                    self._playwright = None


# Global singleton instance per process
_browser_manager: Optional[PlaywrightBrowserManager] = None


def get_browser_manager() -> PlaywrightBrowserManager:
    """Get the global browser manager instance (one per process)."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = PlaywrightBrowserManager()
    return _browser_manager
