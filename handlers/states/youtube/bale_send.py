"""Bale-safe multipart delivery: retry storage upload, never blindly retry user forward."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import logging
import os
from enum import Enum
from typing import Awaitable, Callable, Literal

from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

logger = logging.getLogger(__name__)

MediaKind = Literal["document", "video", "audio"]

PART_SEND_DELAY_SEC = max(1.5, float(os.getenv("BALE_PART_SEND_DELAY_SEC", "2.5")))
STORAGE_UPLOAD_RETRIES = max(1, int(os.getenv("BALE_STORAGE_UPLOAD_RETRIES", "3")))
MAX_FORWARD_RATE_LIMIT_RETRIES = max(1, int(os.getenv("BALE_FORWARD_RATE_LIMIT_RETRIES", "4")))
MAX_RETRY_AFTER_SEC = max(10, int(os.getenv("BALE_MAX_RETRY_AFTER_SEC", "180")))
_BALE_SEND_TIMEOUTS = {
    "read_timeout": 45,
    "write_timeout": 30,
    "connect_timeout": 20,
    "pool_timeout": 20,
}

_CHAT_SEND_LOCKS: OrderedDict[str, asyncio.Lock] = OrderedDict()
_MAX_CHAT_LOCKS = 2000


@asynccontextmanager
async def chat_send_lock(chat_id: str):
    """Serialize cached media deliveries per chat to prevent Bale 504/rate-limit stalls."""
    key = str(chat_id)
    lock = _CHAT_SEND_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _CHAT_SEND_LOCKS[key] = lock
        while len(_CHAT_SEND_LOCKS) > _MAX_CHAT_LOCKS:
            oldest_key, oldest_lock = next(iter(_CHAT_SEND_LOCKS.items()))
            if oldest_lock.locked():
                break
            _CHAT_SEND_LOCKS.pop(oldest_key, None)
    else:
        _CHAT_SEND_LOCKS.move_to_end(key)

    async with lock:
        yield


class ForwardStatus(str, Enum):
    OK = "ok"
    UNCERTAIN = "uncertain"
    FAILED = "failed"


async def forward_file_id_to_user(
    context,
    chat_id: str,
    file_id: str,
    media_kind: MediaKind,
) -> ForwardStatus:
    """
    Deliver an already-uploaded file_id to the user exactly once.

    Bale often returns errors after the message was already delivered; we never
    retry on timeout/ambiguous API errors to avoid duplicate parts.
  """
    async def _send():
        if media_kind == "document":
            await context.bot.send_document(
                chat_id=chat_id,
                document=file_id,
                **_BALE_SEND_TIMEOUTS,
            )
        elif media_kind == "video":
            await context.bot.send_video(
                chat_id=chat_id,
                video=file_id,
                **_BALE_SEND_TIMEOUTS,
            )
        else:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=file_id,
                **_BALE_SEND_TIMEOUTS,
            )

    for attempt in range(1, MAX_FORWARD_RATE_LIMIT_RETRIES + 1):
        try:
            await _send()
            return ForwardStatus.OK
        except RetryAfter as exc:
            # Rate limit — message was not sent yet; safe to wait and retry.
            wait = min(MAX_RETRY_AFTER_SEC, max(2, int(exc.retry_after) + 2))
            logger.warning(
                "RetryAfter %ss before forward to %s (attempt %s/%s)",
                wait,
                chat_id,
                attempt,
                MAX_FORWARD_RATE_LIMIT_RETRIES,
            )
            if attempt >= MAX_FORWARD_RATE_LIMIT_RETRIES:
                return ForwardStatus.FAILED
            await asyncio.sleep(wait)
        except BadRequest as exc:
            logger.warning("Forward BadRequest to %s (not retrying): %s", chat_id, exc)
            return ForwardStatus.FAILED
        except (TimedOut, NetworkError) as exc:
            logger.warning("Forward timeout/network to %s (not retrying): %s", chat_id, exc)
            return ForwardStatus.UNCERTAIN
        except Exception as exc:
            logger.warning("Forward API error to %s (not retrying): %s", chat_id, exc)
            return ForwardStatus.UNCERTAIN
    return ForwardStatus.FAILED


async def run_storage_upload(
    upload_fn: Callable[[], Awaitable[str]],
    *,
    label: str,
) -> str:
    """Retry uploading bytes to the storage channel only (safe to retry)."""
    last_error: Exception | None = None
    for attempt in range(1, STORAGE_UPLOAD_RETRIES + 1):
        try:
            return await upload_fn()
        except RetryAfter as exc:
            wait = max(1, int(exc.retry_after)) + 1
            logger.warning("%s: RetryAfter %ss (attempt %s)", label, wait, attempt)
            await asyncio.sleep(wait)
            last_error = exc
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            logger.warning("%s: network error attempt %s: %s", label, attempt, exc)
            if attempt < STORAGE_UPLOAD_RETRIES:
                await asyncio.sleep(2 * attempt)
        except Exception as exc:
            last_error = exc
            logger.warning("%s: upload error attempt %s: %s", label, attempt, exc)
            if attempt < STORAGE_UPLOAD_RETRIES:
                await asyncio.sleep(2 * attempt)
            else:
                raise
    if last_error:
        raise last_error
    raise RuntimeError(f"{label}: storage upload failed")


async def pause_between_parts(extra_sec: float = 0.0) -> None:
    await asyncio.sleep(PART_SEND_DELAY_SEC + extra_sec)


def adaptive_part_delay(
    part_index: int,
    total_parts: int,
    *,
    status: ForwardStatus = ForwardStatus.OK,
) -> float:
    """Compute Bale-safe delay between forwarded parts to avoid flood/504 stalls."""
    base = PART_SEND_DELAY_SEC if total_parts <= 5 else max(PART_SEND_DELAY_SEC, 3.5)
    extra = 0.0
    if total_parts > 10 and part_index % 10 == 0:
        # Periodic breather so Bale's per-minute rate-limit window resets cleanly.
        extra += 10.0
    if status != ForwardStatus.OK:
        extra += 2.5
    return base + extra


def format_uncertain_parts_message(part_indexes: list[int], total_parts: int) -> str:
    if not part_indexes:
        return ""
    if len(part_indexes) == 1 and part_indexes[0] == 1 and total_parts == 1:
        return (
            "⚠️ ارسال ممکن است انجام شده باشد اما پاسخ بله نامشخص بود.\n"
            "لطفاً چت را بررسی کنید. در صورت نبود فایل، همان لینک را دوباره بفرستید "
            "(از کش ارسال می‌شود)."
        )
    parts_label = "، ".join(str(i) for i in part_indexes)
    return (
        f"⚠️ پارت(های) {parts_label} از {total_parts}: "
        "ممکن است ارسال شده باشند اما بله خطا داد.\n"
        "لطفاً قبل از درخواست مجدد، چت را بررسی کنید تا پارت تکراری دریافت نکنید.\n"
        "برای ارسال دوباره همان ویدیو را از کش می‌توانید درخواست کنید."
    )
