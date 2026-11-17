# core/database/users.py

from .connection import get_db
from .utils import get_tehran_now_full, get_tehran_today
from .web_scrapping import (
    get_web_search_downloads,
    increment_web_search_downloads,
)


async def add_user(user_id, username):
    uid = str(user_id)
    join_date = get_tehran_now_full()
    today = get_tehran_today()
    pool = await get_db()
    await pool.execute(
        """
        INSERT INTO users (
            user_id, username, is_vip, join_date,
            yt_count, yt_date, pinterest_count, pinterest_date
        )
        VALUES ($1, $2, 0, $3, 0, $4, 0, $4)
        ON CONFLICT (user_id) DO NOTHING
        """,
        uid,
        username,
        join_date,
        today,
    )


async def set_vip(user_id, status: int):
    uid = str(user_id)
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET is_vip = $1 WHERE user_id = $2",
        int(status),
        uid,
    )
    from services.cache_service import cache_delete

    await cache_delete(f"vip_status:{uid}")


async def get_user_info(user_id):
    uid = str(user_id)
    pool = await get_db()
    return await pool.fetchrow(
        "SELECT username, is_vip, join_date, vip_expire_date FROM users WHERE user_id = $1",
        uid,
    )


async def get_full_user_info(user_id):
    """Get all user information for admin panel."""
    uid = str(user_id)
    pool = await get_db()
    return await pool.fetchrow(
        """
        SELECT user_id, username, is_vip, join_date, vip_expire_date,
               yt_count, yt_date, music_count, music_date,
               pinterest_count, pinterest_date, tt_dl_count, tt_dl_date,
               gh_count, gh_date
        FROM users WHERE user_id = $1
        """,
        uid,
    )


async def get_total_users() -> int:
    pool = await get_db()
    return int(await pool.fetchval("SELECT COUNT(*) FROM users") or 0)


async def get_all_users() -> list[str]:
    pool = await get_db()
    rows = await pool.fetch("SELECT user_id FROM users")
    return [row["user_id"] for row in rows]


async def get_users_batch(
    after_user_id: str | None = None, limit: int = 100
) -> list[str]:
    """Fetch user IDs in indexed batches using keyset pagination."""
    pool = await get_db()
    if after_user_id is None:
        rows = await pool.fetch(
            "SELECT user_id FROM users ORDER BY user_id ASC LIMIT $1",
            limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT user_id FROM users WHERE user_id > $1 ORDER BY user_id ASC LIMIT $2",
            str(after_user_id),
            limit,
        )
    return [str(row["user_id"]) for row in rows]


async def reset_user_limits(user_id):
    uid = str(user_id)
    pool = await get_db()
    await pool.execute(
        """
        UPDATE users
        SET yt_count = 0, music_count = 0, pinterest_count = 0, tt_dl_count = 0
        WHERE user_id = $1
        """,
        uid,
    )
    from services.rate_limiter import invalidate_cached_usage

    await invalidate_cached_usage(uid)


async def reset_all_user_limits():
    """Reset daily limits for all users (used by admin command)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET yt_count = 0, music_count = 0, pinterest_count = 0"
    )
    from services.rate_limiter import invalidate_all_cached_usage

    await invalidate_all_cached_usage()


__all__ = [
    "add_user",
    "set_vip",
    "get_user_info",
    "get_full_user_info",
    "get_total_users",
    "get_all_users",
    "get_users_batch",
    "reset_user_limits",
    "reset_all_user_limits",
    "get_web_search_downloads",
    "increment_web_search_downloads",
]
