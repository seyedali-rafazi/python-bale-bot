# services/pinterest_queue.py

import asyncio
from typing import List

from services.chromium_workload import heavy_chromium_semaphore
from services.pinterest import search_pinterest_images  

PINTEREST_SEARCH_WORKERS = 1
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
    while True:
        job: PinterestJob = await search_queue.get()

        try:
            print(f"[Pinterest Worker {worker_id}] searching: {job.query}")

            async with heavy_chromium_semaphore:
                # اجرای مستقیم تابع به صورت ناهمگام
                data = await search_pinterest_images(job.query, job.max_results)

            if not job.future.done():
                job.future.set_result(data)

        except Exception as e:
            print(f"Pinterest worker error: {e}")

            if not job.future.done():
                job.future.set_exception(e)

        finally:
            search_queue.task_done()
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

    try:
        await asyncio.wait_for(search_queue.put(job), timeout=45.0)
    except asyncio.TimeoutError:
        if not future.done():
            future.set_result([])
        return []

    return await future
