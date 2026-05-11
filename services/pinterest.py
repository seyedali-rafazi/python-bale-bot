# services/pinterest.py

import re
import html
import aiohttp
import asyncio
from typing import List, Optional, Tuple
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
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def search_images(self, query: str, max_results: int = 30) -> List[str]:
        items = await self._search_rss_items(query=query, max_results=max_results * 2)
        if not items:
            return []

        direct_images = []
        pin_links = []

        for pin_link, desc_image in items:
            if desc_image and desc_image.startswith("http"):
                direct_images.append(desc_image)
            elif pin_link:
                pin_links.append(pin_link)

        direct_images = list(dict.fromkeys(direct_images))
        pin_links = list(dict.fromkeys(pin_links))

        results = []
        seen = set()

        for img in direct_images:
            if img not in seen:
                seen.add(img)
                results.append(img)
            if len(results) >= max_results:
                return results

        if pin_links:
            connector = aiohttp.TCPConnector(limit=10, ssl=False)
            async with aiohttp.ClientSession(
                headers=self.headers, connector=connector
            ) as session:
                tasks = [
                    self._extract_image_from_pin(session, url) for url in pin_links
                ]
                fetched = await asyncio.gather(*tasks, return_exceptions=True)

            for item in fetched:
                if (
                    isinstance(item, str)
                    and item.startswith("http")
                    and item not in seen
                ):
                    seen.add(item)
                    results.append(item)
                if len(results) >= max_results:
                    break

        return results

    async def _search_rss_items(
        self,
        query: str,
        max_results: int = 50,
    ) -> List[Tuple[Optional[str], Optional[str]]]:
        q = quote(query)
        rss_url = (
            f"https://www.pinterest.com/search/pins/"
            f"?q={q}&rs=typed&term_meta[]={q}|typed&add_refine=all&feed=rss"
        )

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    rss_url,
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        print(f"Pinterest RSS status={resp.status}")
                        return []

                    rss_text = await resp.text(errors="ignore")

            return self._extract_items_from_rss_text(rss_text, max_results=max_results)

        except Exception as e:
            print(f"Pinterest RSS search error: {e}")
            return []

    def _extract_items_from_rss_text(
        self,
        rss_text: str,
        max_results: int = 50,
    ) -> List[Tuple[Optional[str], Optional[str]]]:
        items_data = []

        item_blocks = re.findall(
            r"<item\b.*?>.*?</item>", rss_text, flags=re.DOTALL | re.IGNORECASE
        )

        for block in item_blocks:
            link = self._extract_tag(block, "link")
            description = self._extract_tag(block, "description")

            desc_image = self._extract_image_from_description(description or "")

            items_data.append((link, desc_image))

            if len(items_data) >= max_results:
                break

        return items_data

    def _extract_tag(self, text: str, tag: str) -> Optional[str]:
        patterns = [
            rf"<{tag}>(.*?)</{tag}>",
            rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
            if match:
                return html.unescape(match.group(1).strip())

        return None

    def _extract_image_from_description(self, description: str) -> Optional[str]:
        if not description:
            return None

        description = html.unescape(description)

        # اول img src
        img_src = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            description,
            flags=re.IGNORECASE,
        )
        if img_src:
            return img_src.group(1)

        # fallback روی pinimg
        raw_pinimg = re.search(
            r'https://i\.pinimg\.com/[^\s"\']+',
            description,
            flags=re.IGNORECASE,
        )
        if raw_pinimg:
            return raw_pinimg.group(0)

        return None

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
                if resp.status != 200:
                    return None

                text = await resp.text(errors="ignore")

            patterns = [
                r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
                r'https://i\.pinimg\.com/[^\s"\']+',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    return html.unescape(
                        match.group(1) if match.groups() else match.group(0)
                    )

            return None

        except Exception as e:
            print(f"Extract pin image error: {e}")
            return None


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query=query, max_results=max_results)
