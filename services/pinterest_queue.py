# services/pinterest_queue.py

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import List

from services.pinterest import search_pinterest_images

# تعداد سرچ همزمان Pinterest (کاهش یافته برای کاهش مصرف RAM)
PINTEREST_SEARCH_WORKERS = 1

# Use ThreadPoolExecutor instead of ProcessPoolExecutor to avoid asyncio context issues
# ThreadPoolExecutor runs in threads, not processes, but avoids Playwright asyncio conflicts
_process_pool = ThreadPoolExecutor(max_workers=PINTEREST_SEARCH_WORKERS, thread_name_prefix="pinterest-worker")

# queue اصلی سرچ‌ها
search_queue: asyncio.Queue = asyncio.Queue(maxsize=100)


def _isolated_search(query: str, max_results: int) -> List[str]:
    """
    Run Pinterest search in complete isolation from asyncio.
    This wrapper ensures Playwright sync API runs cleanly without asyncio conflicts.
    
    Called from ThreadPoolExecutor to isolate from main asyncio loop.
    """
    try:
        # Import asyncio here (not at module level) to avoid conflicts
        import asyncio
        import sys
        
        # Try to detect if we're somehow in an asyncio context
        try:
            loop = asyncio.get_running_loop()
            # If we get here, there's a loop running (shouldn't happen in thread)
            print(f"⚠️ WARNING: Asyncio loop detected in search thread: {loop}")
        except RuntimeError as e:
            # Expected: No loop running in this thread
            pass
        
        # Now perform the search safely
        result = search_pinterest_images(query, max_results)
        return result
    
    except Exception as e:
        print(f"❌ Error in isolated search for '{query}': {e}")
        import traceback
        traceback.print_exc()
        # Return empty list instead of raising to prevent handler crash
        return []


class PinterestJob:
    def __init__(
        self,
        query: str,
        max_results: int,
        future: asyncio.Future,
    ):
        self.query = query
        self.max_results = max_results
        self.future = future


async def pinterest_worker(worker_id: int):
    loop = asyncio.get_running_loop()

    while True:
        job: PinterestJob = await search_queue.get()

        try:
            print(f"[Pinterest Worker {worker_id}] searching: {job.query}")

            # Use _isolated_search wrapper instead of direct call
            # This ensures Playwright sync API runs cleanly in thread context
            data = await loop.run_in_executor(
                _process_pool,
                _isolated_search,
                job.query,
                job.max_results,
            )

            if not job.future.done():
                job.future.set_result(data)

        except Exception as e:
            print(f"Pinterest worker error: {e}")

            if not job.future.done():
                job.future.set_exception(e)

        finally:
            search_queue.task_done()
            # فاصله بین جستجوها — کاهش بلاک Pinterest/Playwright زیر بار بالا
            await asyncio.sleep(1.5)


async def start_pinterest_workers():
    for i in range(PINTEREST_SEARCH_WORKERS):
        asyncio.create_task(pinterest_worker(i + 1))

    print(f"✅ Started {PINTEREST_SEARCH_WORKERS} Pinterest workers")


async def queued_pinterest_search(
    query: str,
    max_results: int = 30,
) -> List[str]:
    loop = asyncio.get_running_loop()

    future = loop.create_future()

    job = PinterestJob(
        query=query,
        max_results=max_results,
        future=future,
    )
    # اگر صف پر باشد، put بی‌نهایت بلاک می‌کند و کاربر timeout می‌خورد
    try:
        await asyncio.wait_for(search_queue.put(job), timeout=45.0)
    except asyncio.TimeoutError:
        if not future.done():
            future.set_result([])
        return []

    return await future
