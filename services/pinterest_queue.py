# services/pinterest_queue.py

import asyncio
import time
from typing import Dict, List, Tuple

from services.pinterest import search_pinterest_images


# تعداد سرچ همزمان مجاز
PINTEREST_SEARCH_CONCURRENCY = 1

# مدت کش
CACHE_TTL = 1800  # 30 دقیقه

_search_semaphore = asyncio.Semaphore(PINTEREST_SEARCH_CONCURRENCY)
_cache: Dict[str, Tuple[float, List[str]]] = {}
_cache_lock = asyncio.Lock()


async def queued_pinterest_search(query: str, max_results: int = 30) -> List[str]:
    key = query.strip().lower()

    # چک cache
    async with _cache_lock:
        cached = _cache.get(key)
        if cached:
            ts, data = cached
            if time.time() - ts < CACHE_TTL:
                print(f"Pinterest cache hit: {query}")
                return data[:max_results]

    # اجرا در صف
    async with _search_semaphore:
        # چک مجدد cache بعد از انتظار
        async with _cache_lock:
            cached = _cache.get(key)
            if cached:
                ts, data = cached
                if time.time() - ts < CACHE_TTL:
                    print(f"Pinterest cache hit after wait: {query}")
                    return data[:max_results]

        print(f"Pinterest queued search start: {query}")
        data = await search_pinterest_images(query=query, max_results=max_results)

        async with _cache_lock:
            _cache[key] = (time.time(), data)

        return data[:max_results]
