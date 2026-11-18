# core/task_utils.py
"""Shared helpers for tracked background asyncio tasks and non-blocking file cleanup."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Coroutine, Optional, Set

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
