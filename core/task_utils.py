# core/task_utils.py
"""Shared helpers for tracked background asyncio tasks and non-blocking file cleanup."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import shutil
import tempfile
from typing import AsyncIterator, Coroutine, Optional, Set

logger = logging.getLogger(__name__)

_tracked_tasks: Set[asyncio.Task] = set()


def _on_task_done(task: asyncio.Task) -> None:
    _tracked_tasks.discard(task)
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.error(
            "Unhandled exception in tracked background task %s: %s",
            task.get_name(),
            exc,
            exc_info=exc,
        )


def track_task(coro: Coroutine, *, name: Optional[str] = None) -> asyncio.Task:
    """
    Create an asyncio.Task and retain a strong reference until completion.
    Prevents tasks from being garbage-collected mid-flight and allows clean shutdown.
    """
    task = asyncio.create_task(coro, name=name) if name else asyncio.create_task(coro)
    _tracked_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


async def cancel_tracked_tasks(timeout: float = 10.0) -> None:
    """Cancel and await all active tracked background tasks during shutdown."""
    pending = [t for t in list(_tracked_tasks) if not t.done()]
    if not pending:
        return

    logger.info("Cancelling %d tracked background task(s) on shutdown...", len(pending))
    for task in pending:
        task.cancel()

    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Timed out waiting for %d background task(s) to cancel",
            sum(1 for t in pending if not t.done()),
        )


def _remove_sync(path: str) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


async def remove_file_async(path: Optional[str]) -> None:
    """Remove a single file off the asyncio event loop."""
    if not path:
        return
    await asyncio.to_thread(_remove_sync, path)


async def remove_files_async(paths) -> None:
    """Remove multiple files off the asyncio event loop."""
    if not paths:
        return
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    path_list = [str(p) for p in paths if p]
    if not path_list:
        return

    def _remove_many():
        for p in path_list:
            _remove_sync(p)

    await asyncio.to_thread(_remove_many)


@asynccontextmanager
async def async_temp_dir(prefix: str = "bot_tmp_") -> AsyncIterator[str]:
    """Create and clean up a TemporaryDirectory off the asyncio event loop."""
    tmp_dir = await asyncio.to_thread(tempfile.mkdtemp, prefix=prefix)
    try:
        yield tmp_dir
    finally:
        await asyncio.to_thread(shutil.rmtree, tmp_dir, True)


class FileTooLargeError(ValueError):
    """Raised when a streamed download exceeds max_bytes."""


async def stream_aiohttp_to_file(
    resp,
    dest_path: str,
    *,
    chunk_size: int = 512 * 1024,
    max_bytes: Optional[int] = None,
) -> int:
    """Stream an aiohttp response body to disk without blocking the event loop."""
    parent_dir = os.path.dirname(dest_path)
    if parent_dir:
        await asyncio.to_thread(os.makedirs, parent_dir, exist_ok=True)

    f = await asyncio.to_thread(open, dest_path, "wb")
    downloaded = 0
    try:
        async for chunk in resp.content.iter_chunked(chunk_size):
            if not chunk:
                continue
            downloaded += len(chunk)
            if max_bytes is not None and downloaded > max_bytes:
                raise FileTooLargeError(f"Stream exceeded limit ({max_bytes} bytes)")
            await asyncio.to_thread(f.write, chunk)
        return downloaded
    except BaseException:
        await asyncio.to_thread(f.close)
        f = None
        await remove_file_async(dest_path)
        raise
    finally:
        if f is not None:
            await asyncio.to_thread(f.close)
