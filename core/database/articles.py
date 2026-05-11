# core/database/article.py

import aiosqlite
from .base import DB_NAME


async def get_citation_count(user_id: str) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT citation_count FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result and result[0] is not None else 0


async def increment_citation_count(user_id: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "UPDATE users SET citation_count = citation_count + 1 WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()


async def get_book_download_count(user_id: str) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT book_download_count FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result and result[0] is not None else 0


async def increment_book_download_count(user_id: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "UPDATE users SET book_download_count = book_download_count + 1 WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()
