# core/database/counters.py
"""Shared atomic period-based usage counters backed by PostgreSQL + optional Redis cache."""

from __future__ import annotations

from .connection import get_db

_ALLOWED_COUNTER_COLUMNS = frozenset(
    {
        ("yt_count", "yt_date"),
        ("music_count", "music_date"),
        ("pinterest_count", "pinterest_date"),
        ("tt_dl_count", "tt_dl_date"),
        ("gh_count", "gh_date"),
        ("tg_count", "tg_date"),
        ("kaggle_count", "kaggle_date"),
        ("web_search_dl_count", "web_search_dl_date"),
        ("ai_chat_count", "ai_chat_date"),
        ("arc_fetch_count", "arc_fetch_date"),
    }
)


def _validate_columns(count_col: str, date_col: str) -> None:
    if (count_col, date_col) not in _ALLOWED_COUNTER_COLUMNS:
        raise ValueError(f"Unsupported counter columns: {(count_col, date_col)}")


async def get_period_usage(
    user_id: str | int,
    count_col: str,
    date_col: str,
    period_key: str,
    *,
    cache_service: str | None = None,
) -> int:
    """Return user's usage count for period_key (checks Redis cache first when configured)."""
    _validate_columns(count_col, date_col)
    uid = str(user_id)

    if cache_service:
        from services.rate_limiter import get_cached_daily_usage, set_cached_daily_usage

        cached = await get_cached_daily_usage(cache_service, uid, period_key)
        if cached is not None:
            return cached

    pool = await get_db()
    row = await pool.fetchrow(
        f"SELECT {count_col}, {date_col} FROM users WHERE user_id = $1",
        uid,
    )
    actual = 0
    if row is not None and row[date_col] == period_key:
        actual = int(row[count_col] or 0)

    if cache_service:
        from services.rate_limiter import set_cached_daily_usage

        await set_cached_daily_usage(cache_service, uid, period_key, actual)
    return actual


async def increment_period_usage(
    user_id: str | int,
    count_col: str,
    date_col: str,
    period_key: str,
    *,
    monitor_section: str | None = None,
    cache_service: str | None = None,
) -> int:
    """Atomically increment user's counter for period_key and return the new count."""
    _validate_columns(count_col, date_col)
    uid = str(user_id)

    pool = await get_db()
    new_count = await pool.fetchval(
        f"""
        INSERT INTO users (user_id, {count_col}, {date_col})
        VALUES ($1, 1, $2)
        ON CONFLICT (user_id) DO UPDATE SET
            {count_col} = CASE
                WHEN users.{date_col} = $2 THEN COALESCE(users.{count_col}, 0) + 1
                ELSE 1
            END,
            {date_col} = $2
        RETURNING {count_col}
        """,
        uid,
        period_key,
    )
    new_count = int(new_count or 1)

    if cache_service:
        from services.rate_limiter import set_cached_daily_usage

        await set_cached_daily_usage(cache_service, uid, period_key, new_count)

    if monitor_section:
        from .monitoring import log_upload_success

        await log_upload_success(monitor_section, uid)

    return new_count


async def decrement_period_usage(
    user_id: str | int,
    count_col: str,
    date_col: str,
    period_key: str,
    *,
    cache_service: str | None = None,
) -> None:
    """Atomically decrement user's counter for period_key if > 0."""
    _validate_columns(count_col, date_col)
    uid = str(user_id)

    pool = await get_db()
    await pool.execute(
        f"""
        UPDATE users
        SET {count_col} = GREATEST(0, COALESCE({count_col}, 0) - 1)
        WHERE user_id = $1 AND {date_col} = $2 AND COALESCE({count_col}, 0) > 0
        """,
        uid,
        period_key,
    )

    if cache_service:
        from services.rate_limiter import invalidate_cached_usage

        await invalidate_cached_usage(uid, cache_service)
