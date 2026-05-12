# core/database/vip.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from datetime import datetime, timedelta
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم


async def is_vip(user_id):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT is_vip, vip_expire_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()

    if not result:
        return False

    vip_status, expire_date_str = result

    if vip_status == 1:
        if expire_date_str:
            expire_date = datetime.fromisoformat(expire_date_str)
            if datetime.now() > expire_date:
                await conn.execute(
                    "UPDATE users SET is_vip = 0, vip_expire_date = NULL WHERE user_id = ?",
                    (user_id,),
                )
                await conn.commit()
                return False
        return True
    return False


async def add_vip_time(user_id, days: int):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT is_vip, vip_expire_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()

    now = datetime.now()
    if result and result[0] == 1 and result[1]:
        current_expire = datetime.fromisoformat(result[1])
        if current_expire > now:
            new_expire = current_expire + timedelta(days=days)
        else:
            new_expire = now + timedelta(days=days)
    else:
        new_expire = now + timedelta(days=days)

    expire_date_str = new_expire.isoformat()
    await conn.execute(
        "UPDATE users SET is_vip = 1, vip_expire_date = ? WHERE user_id = ?",
        (expire_date_str, user_id),
    )
    await conn.commit()


async def get_total_vip_users():
    now_str = datetime.now().isoformat()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT COUNT(*) FROM users WHERE is_vip = 1 AND (vip_expire_date IS NULL OR vip_expire_date > ?)",
        (now_str,),
    ) as cursor:
        return (await cursor.fetchone())[0]


async def add_vip_time_to_all(days: int) -> int:
    now = datetime.now()
    updated_count = 0
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT user_id, vip_expire_date FROM users WHERE is_vip = 1"
    ) as cursor:
        vip_users = await cursor.fetchall()

    for user_id, expire_str in vip_users:
        if expire_str:
            current_expire = datetime.fromisoformat(expire_str)
            if current_expire > now:
                new_expire = current_expire + timedelta(days=days)
                await conn.execute(
                    "UPDATE users SET vip_expire_date = ? WHERE user_id = ?",
                    (new_expire.isoformat(), user_id),
                )
                updated_count += 1
    await conn.commit()
    return updated_count
