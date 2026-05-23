# services/pinterest_queue.py

import asyncio
import os
from typing import List

from services.chromium_workload import heavy_chromium_semaphore
from services.pinterest import search_pinterest_images

# ۲۰هزار کاربر: یک Chromium مشترک + صف؛ RAM ثابت می‌ماند، تعداد هم‌زمان جستجو محدود است.
PINTEREST_SEARCH_WORKERS = max(1, int(os.getenv("PINTEREST_SEARCH_WORKERS", "1")))
PINTEREST_QUEUE_MAXSIZE = max(20, int(os.getenv("PINTEREST_QUEUE_MAXSIZE", "250")))
PINTEREST_WORKER_DELAY_SEC = max(
    0.0, float(os.getenv("PINTEREST_WORKER_DELAY_SEC", "1.0"))
)
PINTEREST_QUEUE_PUT_TIMEOUT_SEC = max(
    15.0, float(os.getenv("PINTEREST_QUEUE_PUT_TIMEOUT_SEC", "90"))
)
# حداکثر تعداد task پس‌زمینهٔ در حال انتظار (جلوگیری از انفجار حافظهٔ asyncio)
PINTEREST_MAX_IN_FLIGHT = max(
    PINTEREST_QUEUE_MAXSIZE,
    int(os.getenv("PINTEREST_MAX_IN_FLIGHT", str(PINTEREST_QUEUE_MAXSIZE + 50))),
)


search_queue: asyncio.Queue = asyncio.Queue(maxsize=PINTEREST_QUEUE_MAXSIZE)
_in_flight_semaphore = asyncio.Semaphore(PINTEREST_MAX_IN_FLIGHT)


class PinterestQueueFullError(Exception):
    """صف پر است؛ کاربر باید بعداً تلاش کند."""


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


def pinterest_queue_depth() -> int:
    return search_queue.qsize()


def estimate_pinterest_wait_seconds() -> int:
    """تخمین زمان انتظار بر اساس عمق صف (برای پیام به کاربر)."""
    depth = pinterest_queue_depth()
    per_job = 25 + PINTEREST_WORKER_DELAY_SEC
    return min(300, int(30 + depth * per_job / max(PINTEREST_SEARCH_WORKERS, 1)))


def pinterest_search_timeout_seconds() -> float:
    """مهلت کل جستجو: زمان ورود به صف + اجرا."""
    return min(
        300.0,
        PINTEREST_QUEUE_PUT_TIMEOUT_SEC + estimate_pinterest_wait_seconds() + 45.0,
    )


async def pinterest_worker(worker_id: int):
    while True:
        job: PinterestJob = await search_queue.get()

        try:
            print(
                f"[Pinterest Worker {worker_id}] searching: {job.query} "
                f"(queue_remaining≈{search_queue.qsize()})"
            )

            async with heavy_chromium_semaphore:
                data = await search_pinterest_images(job.query, job.max_results)

            if not job.future.done():
                job.future.set_result(data)

        except Exception as e:
            print(f"Pinterest worker error: {e}")

            if not job.future.done():
                job.future.set_exception(e)

        finally:
            search_queue.task_done()
            if PINTEREST_WORKER_DELAY_SEC > 0:
                await asyncio.sleep(PINTEREST_WORKER_DELAY_SEC)


async def start_pinterest_workers():
    for i in range(PINTEREST_SEARCH_WORKERS):
        asyncio.create_task(pinterest_worker(i + 1))

    print(
        f"✅ Started {PINTEREST_SEARCH_WORKERS} Pinterest worker(s) "
        f"(queue={PINTEREST_QUEUE_MAXSIZE}, max_in_flight={PINTEREST_MAX_IN_FLIGHT})"
    )


async def queued_pinterest_search(
    query: str,
    max_results: int = 30,
) -> List[str]:
    if search_queue.full():
        raise PinterestQueueFullError()

    await _in_flight_semaphore.acquire()
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    job = PinterestJob(
        query=query,
        max_results=max_results,
        future=future,
    )

    try:
        try:
            await asyncio.wait_for(
                search_queue.put(job),
                timeout=PINTEREST_QUEUE_PUT_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            if not future.done():
                future.cancel()
            raise PinterestQueueFullError() from None

        return await future
    finally:
        _in_flight_semaphore.release()
