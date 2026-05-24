"""Bale-safe multipart delivery: retry storage upload, never blindly retry user forward."""

from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from typing import Awaitable, Callable, Literal

from telegram.error import NetworkError, RetryAfter, TimedOut

logger = logging.getLogger(__name__)

MediaKind = Literal["document", "video", "audio"]

PART_SEND_DELAY_SEC = max(1.0, float(os.getenv("BALE_PART_SEND_DELAY_SEC", "2.5")))
STORAGE_UPLOAD_RETRIES = max(1, int(os.getenv("BALE_STORAGE_UPLOAD_RETRIES", "3")))
_BALE_SEND_TIMEOUTS = {
    "read_timeout": 180,
    "write_timeout": 180,
    "connect_timeout": 30,
    "pool_timeout": 30,
}


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

    try:
        await _send()
        return ForwardStatus.OK
    except RetryAfter as exc:
        # Rate limit — message was not sent yet; safe to wait and try once more.
        wait = max(1, int(exc.retry_after)) + 1
        logger.warning("RetryAfter %ss before forward to %s", wait, chat_id)
        await asyncio.sleep(wait)
        try:
            await _send()
            return ForwardStatus.OK
        except RetryAfter:
            return ForwardStatus.FAILED
        except (TimedOut, NetworkError) as err:
            logger.warning("Forward uncertain after RetryAfter retry: %s", err)
            return ForwardStatus.UNCERTAIN
        except Exception as err:
            logger.warning("Forward uncertain after RetryAfter retry: %s", err)
            return ForwardStatus.UNCERTAIN
    except (TimedOut, NetworkError) as exc:
        logger.warning("Forward timeout/network to %s (not retrying): %s", chat_id, exc)
        return ForwardStatus.UNCERTAIN
    except Exception as exc:
        logger.warning("Forward API error to %s (not retrying): %s", chat_id, exc)
        return ForwardStatus.UNCERTAIN


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
