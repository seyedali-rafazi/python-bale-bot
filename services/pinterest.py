# services/pinterest.py

import re
import html
import json
import aiohttp
import asyncio
from typing import List, Optional
from urllib.parse import quote


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PinterestService:
    def __init__(self):
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.pinterest.com/",
            "Connection": "keep-alive",
        }

    async def search_images(self, query: str, max_results: int = 30) -> List[str]:
        html_text = await self._fetch_search_page(query)
        if not html_text:
            return []

        results = []

        # 1) مستقیم همه pinimg ها از صفحه
        results.extend(self._extract_pinimg_urls(html_text))

        # 2) استخراج لینک pin ها و رفتن داخل صفحه هر pin
        pin_links = self._extract_pin_links(html_text)
        if pin_links:
            fetched = await self._extract_images_from_pins(pin_links[:20])
            results.extend(fetched)

        # 3) استخراج از JSON های داخل HTML
        results.extend(self._extract_images_from_json_chunks(html_text))

        # normalize + unique
        clean = []
        seen = set()
        for url in results:
            fixed = self._normalize_image_url(url)
            if fixed and fixed not in seen:
                seen.add(fixed)
                clean.append(fixed)
            if len(clean) >= max_results:
                break

        return clean

    async def _fetch_search_page(self, query: str) -> Optional[str]:
        q = quote(query)
        url = f"https://www.pinterest.com/search/pins/?q={q}"

        try:
            connector = aiohttp.TCPConnector(limit=10, ssl=False)
            async with aiohttp.ClientSession(
                headers=self.headers,
                connector=connector,
            ) as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=True,
                ) as resp:
                    print(f"Pinterest search page status={resp.status} url={resp.url}")
                    if resp.status != 200:
                        return None

                    text = await resp.text(errors="ignore")
                    return text
        except Exception as e:
            print(f"_fetch_search_page error: {e}")
            return None

    def _extract_pinimg_urls(self, text: str) -> List[str]:
        urls = re.findall(
            r'https://i\.pinimg\.com/[^\s"\'<>\\)]+',
            text,
            flags=re.IGNORECASE,
        )

        results = []
        seen = set()

        for url in urls:
            url = html.unescape(url.strip())
            url = re.sub(r"\\u002F", "/", url)
            url = url.rstrip("\",'")
            if self._looks_like_image(url) and url not in seen:
                seen.add(url)
                results.append(url)

        return results

    def _extract_pin_links(self, text: str) -> List[str]:
        matches = re.findall(
            r'href=["\'](/pin/\d+/?)["\']',
            text,
            flags=re.IGNORECASE,
        )

        results = []
        seen = set()

        for path in matches:
            url = f"https://www.pinterest.com{path}"
            if url not in seen:
                seen.add(url)
                results.append(url)

        return results

    async def _extract_images_from_pins(self, pin_links: List[str]) -> List[str]:
        connector = aiohttp.TCPConnector(limit=10, ssl=False)
        async with aiohttp.ClientSession(
            headers=self.headers,
            connector=connector,
        ) as session:
            tasks = [self._extract_image_from_pin(session, url) for url in pin_links]
            fetched = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        seen = set()

        for item in fetched:
            if isinstance(item, str):
                item = self._normalize_image_url(item)
                if item and item not in seen:
                    seen.add(item)
                    results.append(item)

        return results

    async def _extract_image_from_pin(
        self,
        session: aiohttp.ClientSession,
        pin_url: str,
    ) -> Optional[str]:
        try:
            async with session.get(
                pin_url,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                print(f"Pin page status={resp.status} url={pin_url}")
                if resp.status != 200:
                    return None

                text = await resp.text(errors="ignore")

            patterns = [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'https://i\.pinimg\.com/[^\s"\'<>\\)]+',
            ]

            for pattern in patterns:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    value = m.group(1) if m.groups() else m.group(0)
                    return html.unescape(value)

            return None

        except Exception as e:
            print(f"_extract_image_from_pin error: {e}")
            return None

    def _extract_images_from_json_chunks(self, text: str) -> List[str]:
        results = []
        seen = set()

        # همه pinimg ها از JSON escaped
        escaped_urls = re.findall(
            r'https:\\/\\/i\.pinimg\.com\\/[^"\']+',
            text,
            flags=re.IGNORECASE,
        )

        for url in escaped_urls:
            fixed = url.replace("\\/", "/")
            fixed = html.unescape(fixed)
            fixed = self._normalize_image_url(fixed)
            if fixed and fixed not in seen:
                seen.add(fixed)
                results.append(fixed)

        # اگر JSONهای script پیدا شد
        script_chunks = re.findall(
            r"<script[^>]*>\s*(\{.*?\})\s*</script>",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        for chunk in script_chunks[:20]:
            try:
                obj = json.loads(chunk)
                found = self._walk_json_for_images(obj)
                for item in found:
                    if item not in seen:
                        seen.add(item)
                        results.append(item)
            except Exception:
                pass

        return results

    def _walk_json_for_images(self, obj) -> List[str]:
        found = []
        seen = set()

        def walk(x):
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                if "i.pinimg.com" in x:
                    fixed = x.replace("\\/", "/")
                    fixed = self._normalize_image_url(fixed)
                    if fixed and fixed not in seen:
                        seen.add(fixed)
                        found.append(fixed)

        walk(obj)
        return found

    def _normalize_image_url(self, url: str) -> Optional[str]:
        if not url:
            return None

        url = html.unescape(url.strip())
        url = url.replace("\\/", "/")
        url = re.sub(r"\\u002F", "/", url)
        url = url.rstrip("\",'")

        if url.startswith("//"):
            url = "https:" + url

        if not url.startswith("http"):
            return None

        if "i.pinimg.com" not in url:
            return None

        if not self._looks_like_image(url):
            return None

        return url

    def _looks_like_image(self, url: str) -> bool:
        return any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"])


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query=query, max_results=max_results)
