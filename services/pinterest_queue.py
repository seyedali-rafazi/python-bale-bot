# services/pinterest_queue.py

import asyncio
import hashlib
import logging
import os
from typing import List

from services.cache_service import cache_get, cache_set
from services.chromium_workload import heavy_chromium_semaphore
from services.pinterest import search_pinterest_images

logger = logging.getLogger(__name__)

# ۲۰هزار کاربر: یک Chromium مشترک + صف؛ RAM ثابت می‌ماند، تعداد هم‌زمان جستجو محدود است.
PINTEREST_SEARCH_WORKERS = max(1, int(os.getenv("PINTEREST_SEARCH_WORKERS", "2")))
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
_inflight_pinterest: dict[str, asyncio.Task] = {}


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
        ran_search = False

        try:
            if job.future.done():
                continue

            logger.info(
                "[Pinterest Worker %s] searching: %s (queue_remaining≈%s)",
                worker_id,
                job.query,
                search_queue.qsize(),
            )

            async with heavy_chromium_semaphore:
                if job.future.done():
                    continue
                ran_search = True
                data = await search_pinterest_images(job.query, job.max_results)

            if not job.future.done():
                job.future.set_result(data)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Pinterest worker error: %s", e)

            if not job.future.done():
                job.future.set_exception(e)

        finally:
            search_queue.task_done()
            if ran_search and PINTEREST_WORKER_DELAY_SEC > 0 and not search_queue.empty():
                await asyncio.sleep(PINTEREST_WORKER_DELAY_SEC)


_worker_tasks: list[asyncio.Task] = []


async def start_pinterest_workers():
    global _worker_tasks
    if any(not t.done() for t in _worker_tasks):
        return
    _worker_tasks = [
        asyncio.create_task(pinterest_worker(i + 1))
        for i in range(PINTEREST_SEARCH_WORKERS)
    ]

    logger.info(
        "✅ Started %s Pinterest worker(s) (queue=%s, max_in_flight=%s)",
        PINTEREST_SEARCH_WORKERS,
        PINTEREST_QUEUE_MAXSIZE,
        PINTEREST_MAX_IN_FLIGHT,
    )


async def stop_pinterest_workers():
    global _worker_tasks
    for task in _worker_tasks:
        if not task.done():
            task.cancel()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()



async def queued_pinterest_search(
    query: str,
    max_results: int = 30,
) -> List[str]:
    clean_q = (query or "").strip()
    cache_key = None
    if clean_q:
        q_hash = hashlib.md5(f"{clean_q.lower()}:{max_results}".encode("utf-8")).hexdigest()[:16]
        cache_key = f"pinterest:search:{q_hash}"
        cached = await cache_get(cache_key)
        if isinstance(cached, list) and cached:
            return cached

    if cache_key:
        existing = _inflight_pinterest.get(cache_key)
        if existing is not None and not existing.done():
            return await asyncio.shield(existing)

    if search_queue.full():
        raise PinterestQueueFullError()

    async def _run_job() -> List[str]:
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

            results = await future
            if cache_key and results:
                await cache_set(cache_key, results, ttl_sec=1200)
            return results
        finally:
            _in_flight_semaphore.release()

    if not cache_key:
        return await _run_job()

    task = asyncio.create_task(_run_job())
    _inflight_pinterest[cache_key] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _inflight_pinterest.get(cache_key) is done_task:
            _inflight_pinterest.pop(cache_key, None)
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)
