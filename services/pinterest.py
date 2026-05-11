# services/pinterest.py

import re
import html
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }

    async def search_images(self, query: str, max_results: int = 30) -> List[str]:
        pin_links = await self._find_pin_links(query, needed=max_results * 3)
        print(f"Pinterest pin links found: {len(pin_links)}")

        if not pin_links:
            return []

        image_urls = await self._extract_images_from_pins(pin_links)

        results = []
        seen = set()

        for url in image_urls:
            norm = self._normalize_image_url(url)
            if norm and norm not in seen:
                seen.add(norm)
                results.append(norm)
            if len(results) >= max_results:
                break

        return results

    async def _find_pin_links(self, query: str, needed: int = 60) -> List[str]:
        search_query = f"{query} site:pinterest.com/pin/"

        providers = [
            self._search_bing,
            self._search_google,
        ]

        results = []
        seen = set()

        for provider in providers:
            try:
                links = await provider(search_query)
                print(f"{provider.__name__} returned {len(links)} links")

                for link in links:
                    norm = self._normalize_pin_url(link)
                    if norm and norm not in seen:
                        seen.add(norm)
                        results.append(norm)
                        if len(results) >= needed:
                            return results

            except Exception as e:
                print(f"{provider.__name__} error: {e}")

        return results

    async def _search_bing(self, query: str) -> List[str]:
        url = f"https://www.bing.com/search?q={quote(query)}&count=50"

        html_text = await self._fetch_text(url, referer="https://www.bing.com/")
        if not html_text:
            return []

        return self._extract_pin_urls_from_search_html(html_text)

    async def _search_google(self, query: str) -> List[str]:
        url = f"https://www.google.com/search?q={quote(query)}&num=50&hl=en"

        html_text = await self._fetch_text(url, referer="https://www.google.com/")
        if not html_text:
            return []

        links = []

        # الگوی لینک‌های redirect گوگل
        for m in re.findall(r'/url\?q=(https?://[^&"\']+)', html_text, flags=re.I):
            links.append(html.unescape(m))

        # گاهی مستقیم هم هست
        links.extend(self._extract_pin_urls_from_search_html(html_text))

        return links

    async def _fetch_text(
        self, url: str, referer: Optional[str] = None
    ) -> Optional[str]:
        headers = dict(self.headers)
        if referer:
            headers["Referer"] = referer

        try:
            connector = aiohttp.TCPConnector(limit=10, ssl=False)
            async with aiohttp.ClientSession(
                headers=headers,
                connector=connector,
            ) as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=True,
                ) as resp:
                    print(f"_fetch_text status={resp.status} url={resp.url}")
                    if resp.status != 200:
                        return None

                    text = await resp.text(errors="ignore")
                    return text
        except Exception as e:
            print(f"_fetch_text error: {e} url={url}")
            return None

    def _extract_pin_urls_from_search_html(self, text: str) -> List[str]:
        matches = re.findall(
            r'https?://(?:[a-z]+\.)?pinterest\.[^/\s"\']+/pin/\d+/?',
            text,
            flags=re.I,
        )

        # بعضی وقت‌ها url encode شده هستند
        encoded_matches = re.findall(
            r'https?%3A%2F%2F(?:[a-z]+\.)?pinterest\.[^"\']+?%2Fpin%2F\d+',
            text,
            flags=re.I,
        )

        results = []
        seen = set()

        for url in matches:
            norm = self._normalize_pin_url(url)
            if norm and norm not in seen:
                seen.add(norm)
                results.append(norm)

        for url in encoded_matches:
            try:
                decoded = (
                    url.replace("%3A", ":")
                    .replace("%2F", "/")
                    .replace("%3F", "?")
                    .replace("%26", "&")
                )
                norm = self._normalize_pin_url(decoded)
                if norm and norm not in seen:
                    seen.add(norm)
                    results.append(norm)
            except Exception:
                pass

        return results

    def _normalize_pin_url(self, url: str) -> Optional[str]:
        if not url:
            return None

        url = html.unescape(url.strip())

        m = re.search(
            r"https?://(?:[a-z]+\.)?pinterest\.[^/]+/pin/(\d+)/?",
            url,
            flags=re.I,
        )
        if not m:
            return None

        pin_id = m.group(1)
        return f"https://www.pinterest.com/pin/{pin_id}/"

    async def _extract_images_from_pins(self, pin_links: List[str]) -> List[str]:
        connector = aiohttp.TCPConnector(limit=10, ssl=False)

        async with aiohttp.ClientSession(
            headers={
                **self.headers,
                "Referer": "https://www.pinterest.com/",
            },
            connector=connector,
        ) as session:
            tasks = [
                self._extract_image_from_pin(session, url) for url in pin_links[:50]
            ]
            fetched = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        seen = set()

        for item in fetched:
            if isinstance(item, str):
                norm = self._normalize_image_url(item)
                if norm and norm not in seen:
                    seen.add(norm)
                    results.append(norm)

        print(f"Pinterest images extracted from pins: {len(results)}")
        return results

    async def _extract_image_from_pin(
        self,
        session: aiohttp.ClientSession,
        pin_url: str,
    ) -> Optional[str]:
        try:
            async with session.get(
                pin_url,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
            ) as resp:
                print(f"Pin page status={resp.status} url={pin_url}")
                if resp.status != 200:
                    return None

                text = await resp.text(errors="ignore")

            patterns = [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'"image_url"\s*:\s*"([^"]+)"',
                r'"orig"\s*:\s*\{\s*"url"\s*:\s*"([^"]+)"',
                r'https://i\.pinimg\.com/[^\s"\'<>\\)]+',
            ]

            for pattern in patterns:
                m = re.search(pattern, text, flags=re.I)
                if m:
                    value = m.group(1) if m.groups() else m.group(0)
                    value = value.replace("\\/", "/")
                    value = html.unescape(value)
                    return value

            return None

        except Exception as e:
            print(f"_extract_image_from_pin error: {e} url={pin_url}")
            return None

    def _normalize_image_url(self, url: str) -> Optional[str]:
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


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query=query, max_results=max_results)
