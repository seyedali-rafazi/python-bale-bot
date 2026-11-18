# services/pinterest.py

import re
import html
import asyncio
import logging
from typing import List, Optional, Dict
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    class PlaywrightTimeoutError(Exception):
        pass


from services.playwright_browser_manager import get_browser_manager

# حجم HTML پینترست بعد از اسکرول می‌تواند چند مگابایت باشد؛ regex روی کل صفحه CPU/RAM می‌سوزاند
_MAX_HTML_FOR_PARSE = 1_500_000
_PINIMG_URL_RE = re.compile(r"https://i\.pinimg\.com/[^\s\"'<>\\)]+", re.IGNORECASE)
# فقط تصاویر واقعی پین‌ها (مسیر سه‌سطحی هش hex و سایزهای پین؛ حذف آیکون‌های UI، _RS و آواتارها)
_REAL_PIN_PATH_RE = re.compile(
    r"^/(originals|1200x|736x|564x|474x|236x)/([0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{2}/[^/?#]+\.(?:jpg|jpeg|png|webp))$",
    re.IGNORECASE,
)
_EXCLUDED_PIN_MARKERS = (
    "_rs/",
    "/webapp/",
    "/avatars/",
    "/custom_covers/",
    "/images/user/",
    "/assets/",
    "/email/",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


_PIN_SIZE_PATH_RE = re.compile(r"/(236x|474x|564x|736x|1200x|originals)/", re.IGNORECASE)


class PinterestService:
    def __init__(self):
        self.user_agent = USER_AGENT

    # این متد باید async باشد چون در داخلش await داریم
    async def search_images(self, query: str, max_results: int = 30) -> List[str]:
        html_text = await self._load_search_page(query)

        # Recovery: HTML می‌آید ولی پین‌های قابل استخراج نیست (صفحه چالش/بلاک)
        if html_text and "i.pinimg.com" not in html_text:
            await get_browser_manager().force_restart()
            await asyncio.sleep(2.0)
            html_text = await self._load_search_page(query, allow_restart=False)

        if not html_text:
            return []

        results = await asyncio.to_thread(
            self._parse_image_urls, html_text, max_results
        )

        logger.info(
            "Pinterest Playwright extracted %s unique high-quality images for query=%s",
            len(results),
            query,
        )

        if results:
            logger.debug("Pinterest sample images: %s", results[:5])

        return results

    def _parse_image_urls(self, html_text: str, max_results: int) -> List[str]:
        raw_urls = self._extract_pinimg_urls(html_text)
        best_by_image: Dict[str, tuple[int, str]] = {}
        verified_originals: set[str] = set()

        for clean_url in raw_urls:
            parsed_path = clean_url.split("i.pinimg.com", 1)[-1]
            m = _REAL_PIN_PATH_RE.match(parsed_path)
            if not m:
                continue
            size_dir = m.group(1).lower()
            image_key = m.group(2).lower()

            if size_dir in ("originals", "1200x"):
                verified_originals.add(image_key)

            best_candidate = _PIN_SIZE_PATH_RE.sub("/originals/", clean_url, count=1)
            cand_score = self._quality_score(best_candidate)
            current = best_by_image.get(image_key)
            if current is None or cand_score < current[0]:
                best_by_image[image_key] = (cand_score, best_candidate)

        sorted_urls = sorted(
            best_by_image.items(),
            key=lambda kv: (0 if kv[0] in verified_originals else 1, kv[1][0]),
        )

        return [kv[1][1] for kv in sorted_urls[:max_results]]

    # این متد به دلیل تعامل با Playwright باید async باشد
    async def _load_search_page(
        self, query: str, *, allow_restart: bool = True
    ) -> Optional[str]:
        search_url = f"https://www.pinterest.com/search/pins/?q={quote(query)}"
        max_retries = 2
        manager = get_browser_manager()

        for attempt in range(max_retries):
            context = None
            page = None
            try:
                context = await manager.new_context(self.user_agent)
                page = await context.new_page()

                async def _block_heavy_resources(route):
                    try:
                        if route.request.resource_type in (
                            "image",
                            "media",
                            "font",
                            "stylesheet",
                        ):
                            await route.abort()
                        else:
                            await route.continue_()
                    except Exception:
                        pass

                await page.route("**/*", _block_heavy_resources)

                await page.set_extra_http_headers(
                    {
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": "https://www.pinterest.com/",
                    }
                )

                logger.info(
                    "Pinterest Playwright opening: %s (attempt %s/%s)",
                    search_url,
                    attempt + 1,
                    max_retries,
                )

                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=35000,
                )

                try:
                    try:
                        await page.wait_for_selector("img[src*='i.pinimg.com']", timeout=4000)
                    except Exception:
                        await page.wait_for_timeout(800)
                    for _ in range(2):
                        await page.mouse.wheel(0, 2000)
                        await page.wait_for_timeout(500)
                except Exception as wait_err:
                    logger.debug("Wait/scroll error (non-critical): %s", wait_err)

                content = ""
                try:
                    extracted = await page.evaluate(
                        """() => {
                            const out = new Set();
                            for (const img of document.querySelectorAll('img[src*="pinimg.com"]')) {
                                if (img.src) out.add(img.src);
                            }
                            const bodyHtml = document.body ? document.body.innerHTML : '';
                            const m = bodyHtml.match(/https?:\\\\?\\/\\\\?\\/i\\.pinimg\\.com[^"'\\s<>\\\\)]+/gi);
                            if (m) for (const u of m) out.add(u);
                            return Array.from(out).join('\\n');
                        }"""
                    )
                    if isinstance(extracted, str) and "i.pinimg.com" in extracted:
                        content = extracted
                except Exception:
                    content = ""

                if not content:
                    content = await page.content()
                if len(content) > _MAX_HTML_FOR_PARSE:
                    content = content[:_MAX_HTML_FOR_PARSE]
                return content

            except PlaywrightTimeoutError as timeout_err:
                logger.warning(
                    "Pinterest timeout for query=%s (attempt %s): %s",
                    query,
                    attempt + 1,
                    timeout_err,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                return None

            except Exception as err:
                logger.warning(
                    "Pinterest error for query=%s (attempt %s): %s",
                    query,
                    attempt + 1,
                    err,
                )
                if attempt < max_retries - 1:
                    err_low = str(err).lower()
                    if allow_restart and any(k in err_low for k in ("closed", "crashed", "disconnected", "target")):
                        await manager.force_restart()
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                return None

            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

        return None

    def _extract_pinimg_urls(self, text: str) -> List[str]:
        if not text:
            return []

        # Skip <head> metadata (og:image, app/social icons, preload badges) when present
        head_end = text.lower().find("</head>")
        body_text = text[head_end + 7 :] if head_end != -1 else text

        normalized = body_text.replace("\\/", "/")
        results = []
        seen = set()

        for url in _PINIMG_URL_RE.findall(normalized):
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

        url = url.split("?")[0]
        lower = url.lower()
        if "i.pinimg.com" not in lower:
            return None
        if any(marker in lower for marker in _EXCLUDED_PIN_MARKERS):
            return None

        try:
            path = urlparse(url).path
        except Exception:
            return None

        if not _REAL_PIN_PATH_RE.match(path):
            return None

        return url

    def _build_quality_candidates(self, url: str, *, already_clean: bool = False) -> List[str]:
        clean = url if already_clean else self._clean_url(url)
        if not clean:
            return []

        candidates = []
        seen = set()

        def add(u: str):
            if u and u not in seen:
                seen.add(u)
                candidates.append(u)

        for target_size in ("originals", "736x", "564x", "474x"):
            add(_PIN_SIZE_PATH_RE.sub(f"/{target_size}/", clean, count=1))
        add(clean)

        candidates.sort(key=self._quality_score)
        return candidates

    def _get_image_key(self, url: str) -> Optional[str]:
        try:
            path = urlparse(url).path
            m = _REAL_PIN_PATH_RE.match(path)
            if not m:
                return None
            return m.group(2).lower()
        except Exception:
            return None

    def _quality_score(self, url: str) -> int:
        lower = url.lower()
        if "/originals/" in lower:
            return 0
        if "/1200x/" in lower:
            return 1
        if "/736x/" in lower:
            return 2
        if "/564x/" in lower:
            return 3
        if "/474x/" in lower:
            return 4
        if "/236x/" in lower:
            return 5
        return 6


# این تابع اصلی که از خارج صدا زده می‌شود نیز باید async باشد
async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    # حتماً باید await شود
    return await service.search_images(query=query, max_results=max_results)
