# services/browser_pool.py
"""
Browser instance pool to prevent RAM exhaustion with concurrent searches.
Reuses browser instances and limits concurrent page creation.
"""

import asyncio
from typing import Optional
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

class BrowserPool:
    """Manages a pool of reusable browser instances with proper resource management."""
    
    def __init__(self, max_browsers: int = 2, max_pages_per_browser: int = 3):
        """
        Args:
            max_browsers: Maximum number of browser instances to keep open
            max_pages_per_browser: Maximum concurrent pages per browser
        """
        self.max_browsers = max_browsers
        self.max_pages_per_browser = max_pages_per_browser
        self.browsers: list[Browser] = []
        self.page_semaphore = asyncio.Semaphore(
            max_browsers * max_pages_per_browser
        )
        self._playwright = None
        self._lock = asyncio.Lock()
        self._current_browser_idx = 0
    
    async def _ensure_initialized(self):
        """Initialize Playwright if needed."""
        if self._playwright is None:
            self._playwright = sync_playwright().__enter__()
    
    async def _create_browser(self) -> Browser:
        """Create a new browser instance with memory-optimized settings."""
        await self._ensure_initialized()
        
        browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",  # Reduce memory usage
                "--disable-web-resources",
                "--disable-extensions",
                "--single-process",  # Use single process to reduce overhead
                "--mute-audio",  # Disable audio
            ],
        )
        return browser
    
    async def get_browser(self) -> Browser:
        """Get an available browser instance, creating one if needed."""
        async with self._lock:
            # Reuse existing browser if available
            if len(self.browsers) < self.max_browsers:
                browser = await self._create_browser()
                self.browsers.append(browser)
                print(f"✅ Created browser instance ({len(self.browsers)}/{self.max_browsers})")
                return browser
            else:
                # Cycle through existing browsers
                browser = self.browsers[self._current_browser_idx % len(self.browsers)]
                self._current_browser_idx += 1
                return browser
    
    async def create_context(self, user_agent: str) -> BrowserContext:
        """Create a new context (tab) in an available browser."""
        browser = await self.get_browser()
        
        context = browser.new_context(
            user_agent=user_agent,
            locale="en-US",
            viewport={"width": 1400, "height": 2200},
            device_scale_factor=1,
        )
        return context
    
    async def close_all(self):
        """Close all browser instances."""
        async with self._lock:
            for browser in self.browsers:
                try:
                    browser.close()
                except Exception as e:
                    print(f"Error closing browser: {e}")
            self.browsers.clear()
            if self._playwright:
                self._playwright.__exit__(None, None, None)
                self._playwright = None
            print("✅ All browsers closed")


# Global singleton instance
_browser_pool: Optional[BrowserPool] = None


async def get_browser_pool() -> BrowserPool:
    """Get or create the global browser pool."""
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPool(max_browsers=2, max_pages_per_browser=3)
    return _browser_pool


async def cleanup_browser_pool():
    """Clean up the browser pool."""
    global _browser_pool
    if _browser_pool:
        await _browser_pool.close_all()
        _browser_pool = None
