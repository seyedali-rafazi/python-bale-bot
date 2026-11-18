# core/database/users.py

from datetime import datetime
from .connection import get_db
from .utils import get_tehran_archive_week_key, get_tehran_now_full, get_tehran_today
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
        SET yt_count = 0, music_count = 0, pinterest_count = 0, tt_dl_count = 0,
            gh_count = 0, tg_count = 0, kaggle_count = 0, web_search_dl_count = 0,
            ai_chat_count = 0, arc_fetch_count = 0
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
        """
        UPDATE users SET yt_count = 0, music_count = 0, pinterest_count = 0,
            tt_dl_count = 0, gh_count = 0, tg_count = 0, kaggle_count = 0,
            web_search_dl_count = 0, ai_chat_count = 0, arc_fetch_count = 0
        WHERE COALESCE(yt_count, 0) != 0
           OR COALESCE(music_count, 0) != 0
           OR COALESCE(pinterest_count, 0) != 0
           OR COALESCE(tt_dl_count, 0) != 0
           OR COALESCE(gh_count, 0) != 0
           OR COALESCE(tg_count, 0) != 0
           OR COALESCE(kaggle_count, 0) != 0
           OR COALESCE(web_search_dl_count, 0) != 0
           OR COALESCE(ai_chat_count, 0) != 0
           OR COALESCE(arc_fetch_count, 0) != 0
        """
    )
    from services.rate_limiter import invalidate_all_cached_usage

    await invalidate_all_cached_usage()


async def get_user_profile_summary(user_id) -> dict | None:
    """Fetch user info, all period usage counters, and cloud stats in one DB query."""
    uid = str(user_id)
    today = get_tehran_today()
    week_key = get_tehran_archive_week_key()
    pool = await get_db()
    row = await pool.fetchrow(
        """
        SELECT
            u.username,
            u.is_vip,
            u.join_date,
            u.vip_expire_date,
            u.yt_count, u.yt_date,
            u.music_count, u.music_date,
            u.pinterest_count, u.pinterest_date,
            u.tt_dl_count, u.tt_dl_date,
            u.gh_count, u.gh_date,
            u.web_search_dl_count, u.web_search_dl_date,
            u.ai_chat_count, u.ai_chat_date,
            u.arc_fetch_count, u.arc_fetch_date,
            u.tg_count, u.tg_date,
            u.cloud_total_mb,
            u.cloud_used_mb,
            COALESCE(cf.file_count, 0) AS cloud_file_count
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS file_count
            FROM cloud_files
            WHERE user_id = $1
            GROUP BY user_id
        ) cf ON cf.user_id = u.user_id
        WHERE u.user_id = $1
        """,
        uid,
    )
    if not row:
        return None

    def _period_val(count_col: str, date_col: str, expected_key: str) -> int:
        return int(row[count_col] or 0) if row[date_col] == expected_key else 0

    is_vip_val = int(row["is_vip"] or 0)
    expire_str = row["vip_expire_date"]
    if is_vip_val == 1 and expire_str:
        try:
            if datetime.now() > datetime.fromisoformat(expire_str):
                is_vip_val = 0
                await pool.execute(
                    "UPDATE users SET is_vip = 0, vip_expire_date = NULL WHERE user_id = $1",
                    uid,
                )
                from services.cache_service import cache_delete

                await cache_delete(f"vip_status:{uid}")
        except ValueError:
            pass
    arc_period_key = today if is_vip_val == 1 else week_key

    return {
        "username": row["username"],
        "is_vip": is_vip_val,
        "join_date": row["join_date"],
        "vip_expire_date": row["vip_expire_date"],
        "yt_count": _period_val("yt_count", "yt_date", today),
        "music_count": _period_val("music_count", "music_date", today),
        "pinterest_count": _period_val("pinterest_count", "pinterest_date", today),
        "tt_dl_count": _period_val("tt_dl_count", "tt_dl_date", today),
        "gh_count": _period_val("gh_count", "gh_date", today),
        "web_search_count": _period_val("web_search_dl_count", "web_search_dl_date", today),
        "ai_count": _period_val("ai_chat_count", "ai_chat_date", today),
        "arc_count": _period_val("arc_fetch_count", "arc_fetch_date", arc_period_key),
        "tg_count": _period_val("tg_count", "tg_date", today),
        "cloud_file_count": int(row["cloud_file_count"] or 0),
        "cloud_total_quota": float(row["cloud_total_mb"] or 0),
        "cloud_used_quota": float(row["cloud_used_mb"] or 0),
    }


__all__ = [
    "add_user",
    "set_vip",
    "get_user_info",
    "get_full_user_info",
    "get_user_profile_summary",
    "get_total_users",
    "get_all_users",
    "get_users_batch",
    "reset_user_limits",
    "reset_all_user_limits",
    "get_web_search_downloads",
    "increment_web_search_downloads",
]
