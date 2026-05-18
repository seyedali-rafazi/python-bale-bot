# core/database/users.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_now_full, get_tehran_today


async def add_user(user_id, username):
    join_date = get_tehran_now_full()
    today = get_tehran_today()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        """
        INSERT OR IGNORE INTO users (user_id, username, is_vip, join_date, yt_count, yt_date, pinterest_count, pinterest_date) 
        VALUES (?, ?, 0, ?, 0, ?, 0, ?)
    """,
        (user_id, username, join_date, today, today),
    )
    await conn.commit()


async def set_vip(user_id, status: int):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        "UPDATE users SET is_vip = ? WHERE user_id = ?", (status, user_id)
    )
    await conn.commit()


async def get_user_info(user_id):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute(
        "SELECT username, is_vip, join_date, vip_expire_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        return await cursor.fetchone()


async def get_full_user_info(user_id):
    """Get all user information for admin panel"""
    conn = await get_db()
    async with conn.execute(
        """SELECT user_id, username, is_vip, join_date, vip_expire_date,
                  yt_count, yt_date, music_count, music_date,
                  pinterest_count, pinterest_date, tt_dl_count, tt_dl_date,
                  tt_exp_count, tt_exp_date, gh_count, gh_date
           FROM users WHERE user_id = ?""",
        (user_id,),
    ) as cursor:
        return await cursor.fetchone()


async def get_total_users():
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
        return (await cursor.fetchone())[0]


async def get_all_users():
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    async with conn.execute("SELECT user_id FROM users") as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def reset_user_limits(user_id):
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        """
        UPDATE users 
        SET yt_count = 0, music_count = 0, pinterest_count = 0, tt_dl_count = 0, tt_exp_count = 0
        WHERE user_id = ?
    """,
        (user_id,),
    )
    await conn.commit()


async def get_web_search_downloads(user_id):
    """Get web search downloads count for today"""
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT web_search_dl_count, web_search_dl_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            count, date = result
            # If date doesn't match today, reset to 0
            if date != today:
                return 0
            return count if count else 0
        return 0


async def increment_web_search_downloads(user_id):
    """Increment web search downloads count and return new count"""
    today = get_tehran_today()
    conn = await get_db()
    
    # Get current count
    async with conn.execute(
        "SELECT web_search_dl_count, web_search_dl_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()
    
    if result:
        current_count, date = result
        # Reset if date changed
        if date != today:
            new_count = 1
        else:
            new_count = (current_count if current_count else 0) + 1
    else:
        new_count = 1
    
    # Update database
    await conn.execute(
        "UPDATE users SET web_search_dl_count = ?, web_search_dl_date = ? WHERE user_id = ?",
        (new_count, today, user_id),
    )
    await conn.commit()
    
    return new_count
