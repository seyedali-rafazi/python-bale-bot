# services/pinterest_queue.py

import asyncio
import functools
from typing import List, Callable, Awaitable, Optional

from services.pinterest import search_pinterest_images


PINTEREST_SEARCH_CONCURRENCY = 1
_search_semaphore = asyncio.Semaphore(PINTEREST_SEARCH_CONCURRENCY)

_queue_lock = asyncio.Lock()
_waiting_count = 0


def _pinterest_search_worker(query: str, max_results: int) -> List[str]:
    """
    تابع در یک Thread جداگانه اجرا می‌شود.
    چون جستجو به طور کامل sync شده، مستقیماً و بدون مشکل در ترد اجرا می‌شود.
    """
    try:
        return search_pinterest_images(query=query, max_results=max_results)
    except Exception as e:
        print(f"Error in _pinterest_search_worker: {e}")
        return []


async def queued_pinterest_search(
    query: str,
    max_results: int = 30,
    on_queue_position: Optional[Callable[[int], Awaitable[None]]] = None,
) -> List[str]:
    global _waiting_count

    async with _queue_lock:
        _waiting_count += 1
        position = _waiting_count

    if on_queue_position:
        try:
            await on_queue_position(position)
        except Exception:
            pass

    try:
        async with _search_semaphore:
            async with _queue_lock:
                _waiting_count -= 1

            print(f"Pinterest queued search start: {query}")

            loop = asyncio.get_running_loop()

            worker_func = functools.partial(
                _pinterest_search_worker, query=query, max_results=max_results
            )

            # اینجا thread کاملا مستقل عمل می‌کند
            data = await loop.run_in_executor(None, worker_func)

            return data[:max_results]

    except Exception:
        async with _queue_lock:
            if _waiting_count > 0:
                _waiting_count -= 1
        raise
