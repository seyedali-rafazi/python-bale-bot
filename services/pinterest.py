# services/pinterest.py

import re
import html
from typing import List, Optional
from urllib.parse import quote

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PinterestService:
    def __init__(self):
        self.user_agent = USER_AGENT

    async def search_images(self, query: str, max_results: int = 30) -> List[str]:
        html_text = await self._load_search_page(query)
        if not html_text:
            return []

        image_urls = self._extract_pinimg_urls(html_text)

        results = []
        seen = set()

        for url in image_urls:
            candidates = self._build_quality_candidates(url)

            for candidate in candidates:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    results.append(candidate)
                    break

            if len(results) >= max_results:
                break

        print(f"Pinterest Playwright extracted {len(results)} images for query={query}")
        return results

    async def _load_search_page(self, query: str) -> Optional[str]:
        search_url = f"https://www.pinterest.com/search/pins/?q={quote(query)}"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )

                context = await browser.new_context(
                    user_agent=self.user_agent,
                    locale="en-US",
                    viewport={"width": 1400, "height": 2200},
                    device_scale_factor=1,
                )

                page = await context.new_page()

                await page.set_extra_http_headers(
                    {
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": "https://www.pinterest.com/",
                    }
                )

                print(f"Pinterest Playwright opening: {search_url}")

                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=45000,
                )

                try:
                    await page.wait_for_timeout(3000)
                    await page.mouse.wheel(0, 2500)
                    await page.wait_for_timeout(2000)
                    await page.mouse.wheel(0, 2500)
                    await page.wait_for_timeout(2000)
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

                content = await page.content()

                await context.close()
                await browser.close()

                return content

        except PlaywrightTimeoutError:
            print(f"Pinterest Playwright timeout for query={query}")
            return None
        except Exception as e:
            print(f"Pinterest Playwright error for query={query}: {e}")
            return None

    def _extract_pinimg_urls(self, text: str) -> List[str]:
        patterns = [
            r'https://i\.pinimg\.com/[^\s"\'<>\\)]+',
            r'https:\\/\\/i\.pinimg\.com\\/[^"\']+',
            r'"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
            r'"image"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
            r'"images"\s*:\s*\{.*?"orig"\s*:\s*\{\s*"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
            r'"images"\s*:\s*\{.*?"736x"\s*:\s*\{\s*"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
            r'"images"\s*:\s*\{.*?"564x"\s*:\s*\{\s*"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
            r'"images"\s*:\s*\{.*?"474x"\s*:\s*\{\s*"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
            r'"images"\s*:\s*\{.*?"236x"\s*:\s*\{\s*"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
        ]

        results = []
        seen = set()

        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.I | re.S)
            for url in matches:
                cleaned = self._clean_url(url)
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    results.append(cleaned)

        return results

    def _clean_url(self, url: str) -> Optional[str]:
        if not url:
            return None

        url = html.unescape(url.strip())
        url = url.replace("\\/", "/")
        url = url.rstrip("\"',")

        if url.startswith("//"):
            url = "https:" + url

        if not url.startswith("http"):
            return None

        if "i.pinimg.com" not in url:
            return None

        return url

    def _build_quality_candidates(self, url: str) -> List[str]:
        """
        از یک URL کم‌کیفیت چند کاندید باکیفیت‌تر می‌سازد.
        ترتیب اهمیت:
        1) originals
        2) 736x
        3) 564x
        4) خود لینک اصلی
        """
        clean = self._clean_url(url)
        if not clean:
            return []

        candidates = []
        seen = set()

        def add(u: str):
            if u and u not in seen:
                seen.add(u)
                candidates.append(u)

        # اگر خودش originals باشد
        add(clean)

        # تبدیل سایزهای thumbnail به originals
        originals_url = re.sub(
            r"/(236x|474x|564x|736x)/",
            "/originals/",
            clean,
            flags=re.I,
        )
        add(originals_url)

        # تبدیل به 736x
        x736_url = re.sub(
            r"/(236x|474x|564x|originals)/",
            "/736x/",
            clean,
            flags=re.I,
        )
        add(x736_url)

        # تبدیل به 564x
        x564_url = re.sub(
            r"/(236x|474x|736x|originals)/",
            "/564x/",
            clean,
            flags=re.I,
        )
        add(x564_url)

        # اگر URL شامل originals بود، نسخه 736x هم ساخته شود
        if "/originals/" in clean:
            add(clean.replace("/originals/", "/736x/"))

        # اولویت‌بندی بهتر:
        def score(u: str) -> int:
            if "/originals/" in u:
                return 0
            if "/736x/" in u:
                return 1
            if "/564x/" in u:
                return 2
            if "/474x/" in u:
                return 3
            if "/236x/" in u:
                return 4
            return 5

        candidates.sort(key=score)
        return candidates


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query=query, max_results=max_results)
