# services/pinterest.py

import json
import aiohttp
import asyncio
from typing import List, Dict, Optional


PINTEREST_SEARCH_URL = "https://www.pinterest.com/resource/BaseSearchResource/get/"


class PinterestService:
    def __init__(self):
        self.base_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*, q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.pinterest.com/",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def search_images(
        self,
        query: str,
        max_results: int = 30,
        timeout: int = 15,
    ) -> List[str]:
        """
        جستجوی مستقیم در پینترست و استخراج URL عکس‌ها
        """
        bookmarks = ["-end-"]
        results = []
        seen = set()

        async with aiohttp.ClientSession(headers=self.base_headers) as session:
            while len(results) < max_results and bookmarks:
                data = await self._fetch_search_page(
                    session=session,
                    query=query,
                    bookmarks=bookmarks,
                    timeout=timeout,
                )

                if not data:
                    break

                resource_response = data.get("resource_response", {})
                response_data = resource_response.get("data", {})

                items = response_data.get("results", [])
                if not items:
                    break

                for item in items:
                    image_url = self._extract_best_image(item)
                    if image_url and image_url not in seen:
                        seen.add(image_url)
                        results.append(image_url)

                        if len(results) >= max_results:
                            break

                bookmarks = (
                    response_data.get("bookmark")
                    or response_data.get("bookmarks")
                    or []
                )

                if isinstance(bookmarks, str):
                    bookmarks = [bookmarks]

                if not bookmarks or bookmarks == ["-end-"]:
                    break

        return results

    async def _fetch_search_page(
        self,
        session: aiohttp.ClientSession,
        query: str,
        bookmarks: List[str],
        timeout: int,
    ) -> Optional[Dict]:
        try:
            params = {
                "source_url": f"/search/pins/?q={query}",
                "data": json.dumps(
                    {
                        "options": {
                            "query": query,
                            "scope": "pins",
                            "bookmarks": bookmarks,
                            "no_fetch_context_on_resource": False,
                        },
                        "context": {},
                    }
                ),
                "_": "1",
            }

            async with session.get(
                PINTEREST_SEARCH_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"Pinterest status={resp.status}, body={text[:300]}")
                    return None

                return await resp.json()

        except Exception as e:
            print(f"Pinterest fetch search page error: {e}")
            return None

    def _extract_best_image(self, item: Dict) -> Optional[str]:
        """
        تلاش برای پیدا کردن بهترین URL تصویر از ساختارهای مختلف داده Pinterest
        """
        try:
            if not isinstance(item, dict):
                return None

            # حالت رایج
            images = item.get("images", {})
            if isinstance(images, dict):
                for key in ("orig", "564x", "474x", "236x"):
                    if key in images and isinstance(images[key], dict):
                        url = images[key].get("url")
                        if url:
                            return url

                # fallback
                for _, val in images.items():
                    if isinstance(val, dict):
                        url = val.get("url")
                        if url:
                            return url

            # حالت imageSignature / image_spec / grid تصاویر
            image_spec = item.get("image_spec")
            if isinstance(image_spec, dict):
                url = image_spec.get("url")
                if url:
                    return url

            # حالت fallback مستقیم
            for field in ("image_url", "url", "orig_image"):
                val = item.get(field)
                if isinstance(val, str) and val.startswith("http"):
                    return val
                if isinstance(val, dict):
                    url = val.get("url")
                    if url:
                        return url

        except Exception as e:
            print(f"Pinterest extract image error: {e}")

        return None


async def search_pinterest_images(query: str, max_results: int = 30) -> List[str]:
    service = PinterestService()
    return await service.search_images(query=query, max_results=max_results)
