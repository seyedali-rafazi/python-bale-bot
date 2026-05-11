# services/pinterest.py

import re
import html
from typing import List, Optional, Dict
from urllib.parse import quote, urlparse

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

        raw_urls = self._extract_pinimg_urls(html_text)

        best_by_image: Dict[str, str] = {}

        for raw_url in raw_urls:
            clean_url = self._clean_url(raw_url)
            if not clean_url:
                continue

            candidates = self._build_quality_candidates(clean_url)

            for candidate in candidates:
                image_key = self._get_image_key(candidate)
                if not image_key:
                    continue

                current = best_by_image.get(image_key)

                if not current:
                    best_by_image[image_key] = candidate
                else:
                    if self._quality_score(candidate) < self._quality_score(current):
                        best_by_image[image_key] = candidate

        sorted_urls = sorted(
            best_by_image.values(),
            key=lambda u: self._quality_score(u),
        )

        results = sorted_urls[:max_results]

        print(
            f"Pinterest Playwright extracted {len(results)} unique high-quality images for query={query}"
        )

        if results:
            print("Pinterest sample images:", results[:5])

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

                    for _ in range(4):
                        await page.mouse.wheel(0, 2500)
                        await page.wait_for_timeout(1500)

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
            r'"images"\s*:\s*\{.*?"originals"\s*:\s*\{\s*"url"\s*:\s*"(https:\\/\\/i\.pinimg\.com\\/[^"]+)"',
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
        url = url.rstrip("\"',);")

        if url.startswith("//"):
            url = "https:" + url

        if not url.startswith("http"):
            return None

        if "i.pinimg.com" not in url:
            return None

        # حذف query string اگر وجود داشت
        url = url.split("?")[0]

        return url

    def _build_quality_candidates(self, url: str) -> List[str]:
        """
        برای هر URL، فقط کاندیدهای کیفیت بالاتر می‌سازد.
        بعداً بر اساس image_key فقط بهترینشان انتخاب می‌شود.
        """
        clean = self._clean_url(url)
        if not clean:
            return []

        candidates = []
        seen = set()

        def add(u: str):
            u = self._clean_url(u)
            if u and u not in seen:
                seen.add(u)
                candidates.append(u)

        # نسخه‌های احتمالی بهتر
        originals_url = re.sub(
            r"/(236x|474x|564x|736x)/",
            "/originals/",
            clean,
            flags=re.I,
        )

        x736_url = re.sub(
            r"/(236x|474x|564x|originals)/",
            "/736x/",
            clean,
            flags=re.I,
        )

        x564_url = re.sub(
            r"/(236x|474x|736x|originals)/",
            "/564x/",
            clean,
            flags=re.I,
        )

        x474_url = re.sub(
            r"/(236x|564x|736x|originals)/",
            "/474x/",
            clean,
            flags=re.I,
        )

        x236_url = re.sub(
            r"/(474x|564x|736x|originals)/",
            "/236x/",
            clean,
            flags=re.I,
        )

        # ترتیب اضافه کردن مهم است
        add(originals_url)
        add(x736_url)
        add(x564_url)
        add(x474_url)
        add(x236_url)
        add(clean)

        candidates.sort(key=self._quality_score)

        return candidates

    def _get_image_key(self, url: str) -> Optional[str]:
        """
        کلید یکتا برای تشخیص اینکه چند URL با سایزهای مختلف مربوط به یک عکس هستند.

        مثال:
        https://i.pinimg.com/236x/aa/bb/cc/img.jpg
        https://i.pinimg.com/736x/aa/bb/cc/img.jpg
        https://i.pinimg.com/originals/aa/bb/cc/img.jpg

        همه تبدیل می‌شوند به:
        aa/bb/cc/img.jpg
        """
        clean = self._clean_url(url)
        if not clean:
            return None

        try:
            parsed = urlparse(clean)
            path = parsed.path

            path = re.sub(
                r"^/(236x|474x|564x|736x|originals)/",
                "",
                path,
                flags=re.I,
            )

            return path.lower()

        except Exception:
            return None

    def _quality_score(self, url: str) -> int:
        """
        عدد کمتر یعنی کیفیت بهتر.
        """
        if "/originals/" in url:
            return 0
        if "/736x/" in url:
            return 1
        if "/564x/" in url:
            return 2
        if "/474x/" in url:
            return 3
        if "/236x/" in url:
            return 4
        return 5


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query=query, max_results=max_results)
