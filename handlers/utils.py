# handlers/utils.py
"""Shared helpers for Telegram/Bale handlers (Markdown escaping, safe UI calls, S3 cloud uploads)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Sequence

from core.task_utils import get_file_size_async

logger = logging.getLogger(__name__)


def escape_markdown(text: object) -> str:
    """Escape Telegram legacy Markdown v1 special characters in user/external strings."""
    if text is None:
        return ""
    s = str(text)
    for ch in ("_", "*", "`", "["):
        s = s.replace(ch, f"\\{ch}")
    return s


async def safe_answer_query(query, text: str | None = None, *, show_alert: bool = False) -> None:
    if query is None:
        return
    try:
        if text is not None:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
    except Exception:
        pass


async def safe_edit_or_reply(msg, text: str, **kwargs) -> None:
    if msg is None:
        return
    try:
        await msg.edit_text(text, **kwargs)
    except Exception:
        try:
            await msg.reply_text(text, **kwargs)
        except Exception:
            pass


async def upload_paths_to_cloud_s3(
    chat_id: str,
    file_paths: Sequence[str],
    progress_dict: dict | None = None,
    *,
    object_names: Sequence[str | None] | None = None,
    reserve_fn: Callable,
    release_fn: Callable,
    avail_fn: Callable,
    record_fn: Callable,
    upload_async_fn: Callable | None,
    upload_sync_fn: Callable | None,
) -> dict:
    """
    Atomically reserve cloud quota, upload one or more local files to S3,
    and record the uploads in PostgreSQL.

    Returns dict:
      - {"status": "insufficient_quota", "needed_mb": float, "available_mb": float}
      - {"status": "upload_failed"}
      - {"status": "ok", "links": list[str], "total_mb": float}
    """
    if not file_paths:
        return {"status": "upload_failed"}

    total_needed_mb = 0.0
    for fp in file_paths:
        total_needed_mb += round((await get_file_size_async(fp)) / (1024 * 1024), 2)

    reserved = await reserve_fn(chat_id, total_needed_mb)
    if not reserved:
        avail = await avail_fn(chat_id)
        if avail is None or avail <= 0:
            avail = 0.0
        return {
            "status": "insufficient_quota",
            "needed_mb": total_needed_mb,
            "available_mb": round(float(avail), 2),
        }

    s3_links: list[str] = []
    cloud_records: list[tuple[str, float, str, str | None]] = []
    actual_total_mb = 0.0

    try:
        for idx, file_path in enumerate(file_paths):
            obj_name = object_names[idx] if object_names and idx < len(object_names) else None
            if upload_sync_fn is not None:
                if upload_async_fn is not None:
                    s3_url, s3_key = await upload_async_fn(
                        file_path,
                        obj_name,
                        progress_dict,
                        upload_fn=upload_sync_fn,
                    )
                else:
                    s3_url, s3_key = await asyncio.to_thread(
                        upload_sync_fn,
                        file_path,
                        obj_name,
                        progress_dict,
                    )
            else:
                s3_url, s3_key = None, None

            if s3_url:
                file_size_mb = round(
                    (await get_file_size_async(file_path)) / (1024 * 1024),
                    2,
                )
                file_name = obj_name.rsplit("/", 1)[-1] if obj_name else os.path.basename(file_path)
                actual_total_mb += file_size_mb
                cloud_records.append((file_name, file_size_mb, s3_url, s3_key))
                s3_links.append(s3_url)
    except BaseException:
        try:
            await release_fn(chat_id, total_needed_mb)
        except Exception:
            logger.exception("Failed releasing cloud quota for %s", chat_id)
        raise

    if not s3_links:
        await release_fn(chat_id, total_needed_mb)
        return {"status": "upload_failed"}

    diff = total_needed_mb - actual_total_mb
    if diff > 0:
        await release_fn(chat_id, diff)

    await record_fn(chat_id, cloud_records, quota_reserved=True)
    return {
        "status": "ok",
        "links": s3_links,
        "total_mb": round(actual_total_mb, 2),
    }
