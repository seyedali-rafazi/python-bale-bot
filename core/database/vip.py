# core/database/vip.py

from datetime import datetime, timedelta
from .connection import get_db


async def is_vip(user_id) -> bool:
    uid = str(user_id)
    from services.cache_service import cache_get, cache_set

    cache_key = f"vip_status:{uid}"
    cached_status = await cache_get(cache_key)
    if cached_status is not None:
        return bool(cached_status)

    pool = await get_db()
    result = await pool.fetchrow(
        "SELECT is_vip, vip_expire_date FROM users WHERE user_id = $1",
        uid,
    )

    if not result:
        await cache_set(cache_key, 0, ttl_sec=300)
        return False

    vip_status = result["is_vip"]
    expire_date_str = result["vip_expire_date"]

    if vip_status == 1:
        if expire_date_str:
            expire_date = datetime.fromisoformat(expire_date_str)
            if datetime.now() > expire_date:
                await pool.execute(
                    "UPDATE users SET is_vip = 0, vip_expire_date = NULL WHERE user_id = $1",
                    uid,
                )
                await cache_set(cache_key, 0, ttl_sec=300)
                return False
        await cache_set(cache_key, 1, ttl_sec=300)
        return True

    await cache_set(cache_key, 0, ttl_sec=300)
    return False


async def add_vip_time(user_id, days: int):
    uid = str(user_id)
    pool = await get_db()

    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.fetchrow(
                "SELECT is_vip, vip_expire_date FROM users WHERE user_id = $1 FOR UPDATE",
                uid,
            )

            now = datetime.now()
            if result and result["is_vip"] == 1 and result["vip_expire_date"]:
                current_expire = datetime.fromisoformat(result["vip_expire_date"])
                base = current_expire if current_expire > now else now
            else:
                base = now

            expire_date_str = (base + timedelta(days=days)).isoformat()
            await conn.execute(
                """
                INSERT INTO users (user_id, is_vip, vip_expire_date)
                VALUES ($1, 1, $2)
                ON CONFLICT (user_id) DO UPDATE SET
                    is_vip = 1,
                    vip_expire_date = EXCLUDED.vip_expire_date
                """,
                uid,
                expire_date_str,
            )

    from services.cache_service import cache_delete

    await cache_delete(f"vip_status:{uid}")


async def get_total_vip_users() -> int:
    now_str = datetime.now().isoformat()
    pool = await get_db()
    return int(
        await pool.fetchval(
            "SELECT COUNT(*) FROM users WHERE is_vip = 1 AND (vip_expire_date IS NULL OR vip_expire_date > $1)",
            now_str,
        )
        or 0
    )


async def set_vip_expire_date(user_id, days: int):
    """Set VIP expire date to X days from now."""
    uid = str(user_id)
    pool = await get_db()
    try:
        now = datetime.now()
        expire_date = now + timedelta(days=days)
        expire_iso = expire_date.isoformat()

        await pool.execute(
            "UPDATE users SET is_vip = 1, vip_expire_date = $1 WHERE user_id = $2",
            expire_iso,
            uid,
        )
        from services.cache_service import cache_delete

        await cache_delete(f"vip_status:{uid}")
        return True, expire_date
    except (ValueError, TypeError):
        return False, None


async def add_vip_time_to_all(days: int) -> int:
    now = datetime.now()
    pool = await get_db()
    updates: list[tuple[str, str]] = []
    updated_user_ids: list[str] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            vip_users = await conn.fetch(
                "SELECT user_id, vip_expire_date FROM users WHERE is_vip = 1 FOR UPDATE"
            )
            for row in vip_users:
                expire_str = row["vip_expire_date"]
                if expire_str:
                    current_expire = datetime.fromisoformat(expire_str)
                    if current_expire > now:
                        new_expire = current_expire + timedelta(days=days)
                        updates.append((new_expire.isoformat(), row["user_id"]))
                        updated_user_ids.append(row["user_id"])

            if updates:
                await conn.executemany(
                    "UPDATE users SET vip_expire_date = $1 WHERE user_id = $2",
                    updates,
                )

    if updated_user_ids:
        from services.cache_service import cache_delete

        for uid in updated_user_ids:
            await cache_delete(f"vip_status:{uid}")

    return len(updates)
