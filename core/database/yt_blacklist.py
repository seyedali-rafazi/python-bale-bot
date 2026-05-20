# core/database/yt_blacklist.py

from .connection import get_db
from .utils import get_tehran_now_full


def normalize_channel_key(name: str) -> str:
    if not name:
        return ""
    return name.strip().lower().lstrip("@").replace(" ", "")


async def add_channel_blacklist(channel: str) -> bool:
    key = normalize_channel_key(channel)
    if not key or len(key) < 2:
        return False
    conn = await get_db()
    await conn.execute(
        """
        INSERT OR IGNORE INTO yt_channel_blacklist (channel_key, display_name, added_at)
        VALUES (?, ?, ?)
        """,
        (key, channel.strip()[:200], get_tehran_now_full()),
    )
    await conn.commit()
    return True


async def remove_channel_blacklist(channel: str) -> bool:
    key = normalize_channel_key(channel)
    conn = await get_db()
    cursor = await conn.execute(
        "DELETE FROM yt_channel_blacklist WHERE channel_key = ?", (key,)
    )
    await conn.commit()
    return cursor.rowcount > 0


async def list_channel_blacklist():
    conn = await get_db()
    async with conn.execute(
        """
        SELECT channel_key, display_name, added_at
        FROM yt_channel_blacklist
        ORDER BY added_at DESC
        """
    ) as cursor:
        return await cursor.fetchall()


async def get_all_channel_blacklist_keys():
    conn = await get_db()
    async with conn.execute(
        "SELECT channel_key FROM yt_channel_blacklist"
    ) as cursor:
        rows = await cursor.fetchall()
        return [row["channel_key"] for row in rows]


async def is_channel_blacklisted(*names: str) -> bool:
    keys = await get_all_channel_blacklist_keys()
    if not keys:
        return False
    for raw in names:
        if not raw:
            continue
        norm = normalize_channel_key(raw)
        compact = raw.strip().lower()
        for bl in keys:
            if bl == norm or bl in norm or norm in bl:
                return True
            if bl in compact or compact in bl:
                return True
    return False


async def add_blocked_word(word: str) -> bool:
    w = word.strip().lower()
    if len(w) < 2:
        return False
    conn = await get_db()
    await conn.execute(
        """
        INSERT OR IGNORE INTO yt_blocked_words (word, added_at)
        VALUES (?, ?)
        """,
        (w, get_tehran_now_full()),
    )
    await conn.commit()
    return True


async def remove_blocked_word(word: str) -> bool:
    w = word.strip().lower()
    conn = await get_db()
    cursor = await conn.execute(
        "DELETE FROM yt_blocked_words WHERE word = ?", (w,)
    )
    await conn.commit()
    return cursor.rowcount > 0


async def list_blocked_words():
    conn = await get_db()
    async with conn.execute(
        "SELECT word, added_at FROM yt_blocked_words ORDER BY word ASC"
    ) as cursor:
        return await cursor.fetchall()


async def get_all_blocked_words():
    conn = await get_db()
    async with conn.execute("SELECT word FROM yt_blocked_words") as cursor:
        rows = await cursor.fetchall()
        return [row["word"] for row in rows]


async def seed_default_blocked_words(default_words: list[str]):
    conn = await get_db()
    now = get_tehran_now_full()
    for word in default_words:
        w = word.strip().lower()
        if len(w) < 2:
            continue
        await conn.execute(
            "INSERT OR IGNORE INTO yt_blocked_words (word, added_at) VALUES (?, ?)",
            (w, now),
        )
    await conn.commit()
