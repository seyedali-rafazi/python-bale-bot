# services/pinterest.py

import re
import html
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
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
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def search_images(self, query: str, max_results: int = 30) -> List[str]:
        pin_links = await self._search_pin_links_via_rss(
            query, max_results=max_results * 2
        )
        if not pin_links:
            return []

        pin_links = list(dict.fromkeys(pin_links))[: max_results * 2]

        connector = aiohttp.TCPConnector(limit=10, ssl=False)
        async with aiohttp.ClientSession(
            headers=self.headers, connector=connector
        ) as session:
            tasks = [self._extract_image_from_pin(session, url) for url in pin_links]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        images = []
        seen = set()

        for item in results:
            if isinstance(item, str) and item.startswith("http"):
                if item not in seen:
                    seen.add(item)
                    images.append(item)
            if len(images) >= max_results:
                break

        return images

    async def _search_pin_links_via_rss(
        self, query: str, max_results: int = 50
    ) -> List[str]:
        q = quote(query)
        rss_url = (
            f"https://www.pinterest.com/search/pins/"
            f"?q={q}&rs=typed&term_meta[]={q}|typed&add_refine=all&feed=rss"
        )

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    rss_url, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        print(f"Pinterest RSS status={resp.status}")
                        return []

                    xml_text = await resp.text()

            root = ET.fromstring(xml_text)
            items = root.findall(".//item")

            links = []
            for item in items:
                link_el = item.find("link")
                if link_el is not None and link_el.text:
                    links.append(link_el.text.strip())
                if len(links) >= max_results:
                    break

            return links

        except Exception as e:
            print(f"Pinterest RSS search error: {e}")
            return []

    async def _extract_image_from_pin(
        self, session: aiohttp.ClientSession, pin_url: str
    ) -> Optional[str]:
        try:
            async with session.get(
                pin_url,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return None

                text = await resp.text()

            # 1) og:image
            og_match = re.search(
                r'<meta\s+property="og:image"\s+content="([^"]+)"',
                text,
                re.IGNORECASE,
            )
            if og_match:
                return html.unescape(og_match.group(1))

            # 2) twitter:image
            tw_match = re.search(
                r'<meta\s+name="twitter:image"\s+content="([^"]+)"',
                text,
                re.IGNORECASE,
            )
            if tw_match:
                return html.unescape(tw_match.group(1))

            # 3) fallback direct image URL in html
            img_match = re.search(
                r'https://i\.pinimg\.com/[^\s"\']+',
                text,
                re.IGNORECASE,
            )
            if img_match:
                return html.unescape(img_match.group(0))

            return None

        except Exception as e:
            print(f"Extract pin image error: {e}")
            return None


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query, max_results=max_results)
