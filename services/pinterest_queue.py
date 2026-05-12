# services/pinterest_queue.py

import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import List, Callable, Awaitable, Optional

from services.pinterest import search_pinterest_images

PINTEREST_SEARCH_CONCURRENCY = 1
_search_semaphore = asyncio.Semaphore(PINTEREST_SEARCH_CONCURRENCY)

_queue_lock = asyncio.Lock()
_waiting_count = 0

_process_pool = ProcessPoolExecutor(max_workers=PINTEREST_SEARCH_CONCURRENCY)


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

            # اجرای در پروسه جداگانه
            data = await loop.run_in_executor(
                _process_pool, search_pinterest_images, query, max_results
            )

            return data[:max_results]

    except Exception as e:
        print(f"Pinterest ProcessPool error: {e}")
        async with _queue_lock:
            if _waiting_count > 0:
                _waiting_count -= 1
        raise
