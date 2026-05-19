# services/pinterest_queue.py

import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import List

from services.pinterest import search_pinterest_images

# تعداد سرچ همزمان Pinterest (کاهش یافته برای کاهش مصرف RAM)
# هر worker با یک process اجرا می‌شود و اکنون یک browser shared دارد
PINTEREST_SEARCH_WORKERS = 1

# تعداد worker واقعی
_process_pool = ProcessPoolExecutor(max_workers=PINTEREST_SEARCH_WORKERS)

# queue اصلی سرچ‌ها (queue size را نیز کاهش دادیم)
search_queue: asyncio.Queue = asyncio.Queue(maxsize=100)


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

            data = await loop.run_in_executor(
                _process_pool,
                search_pinterest_images,
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
            # Add small delay between searches to prevent overwhelming system
            await asyncio.sleep(0.5)


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

    await search_queue.put(
        PinterestJob(
            query=query,
            max_results=max_results,
            future=future,
        )
    )

    return await future
