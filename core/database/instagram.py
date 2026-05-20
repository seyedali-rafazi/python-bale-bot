# core/database/instagram.py

from .connection import get_db
from .utils import get_tehran_today


async def get_ig_downloads(user_id):
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT ig_dl_count, ig_dl_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            return 0 if result[1] != today else result[0]
        return 0


async def increment_ig_downloads(user_id):
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT ig_dl_count, ig_dl_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
    if result:
        new_count = 1 if result[1] != today else result[0] + 1
        await conn.execute(
            "UPDATE users SET ig_dl_count = ?, ig_dl_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    await conn.commit()


async def get_ig_explores(user_id):
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT ig_exp_count, ig_exp_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            return 0 if result[1] != today else result[0]
        return 0


async def increment_ig_explores(user_id):
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT ig_exp_count, ig_exp_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
    if result:
        new_count = 1 if result[1] != today else result[0] + 1
        await conn.execute(
            "UPDATE users SET ig_exp_count = ?, ig_exp_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    await conn.commit()


async def add_instagram_explore_media(file_id):
    conn = await get_db()
    await conn.execute(
        "INSERT OR IGNORE INTO instagram_explore (file_id) VALUES (?)", (file_id,)
    )
    await conn.commit()


async def get_random_instagram_explore_media(limit=5):
    conn = await get_db()
    async with conn.execute(
        "SELECT file_id FROM instagram_explore ORDER BY RANDOM() LIMIT ?", (limit,)
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def delete_invalid_ig_from_db(file_id: str):
    conn = await get_db()
    await conn.execute("DELETE FROM instagram_explore WHERE file_id = ?", (file_id,))
    await conn.commit()
