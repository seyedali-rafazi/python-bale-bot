# core/database/yt_blacklist.py

import time
from .connection import get_db
from .utils import get_tehran_now_full

_CHANNEL_BLACKLIST_CACHE_KEY = "yt_blacklist:channels"
_BLOCKED_WORDS_CACHE_KEY = "yt_blacklist:words"
_L1_TTL_SEC = 60.0
_l1_lists: dict[str, tuple[list[str], float]] = {}


def _l1_get(key: str) -> list[str] | None:
    entry = _l1_lists.get(key)
    if entry is not None:
        val, exp = entry
        if time.monotonic() < exp:
            return val
        _l1_lists.pop(key, None)
    return None


def _l1_set(key: str, val: list[str]) -> None:
    _l1_lists[key] = (val, time.monotonic() + _L1_TTL_SEC)


def _l1_del(key: str) -> None:
    _l1_lists.pop(key, None)


def normalize_channel_key(name: str) -> str:
    if not name:
        return ""
    return name.strip().lower().lstrip("@").replace(" ", "")


async def add_channel_blacklist(channel: str) -> bool:
    key = normalize_channel_key(channel)
    if not key or len(key) < 2:
        return False
    pool = await get_db()
    await pool.execute(
        """
        INSERT INTO yt_channel_blacklist (channel_key, display_name, added_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (channel_key) DO NOTHING
        """,
        key,
        channel.strip()[:200],
        get_tehran_now_full(),
    )
    from services.cache_service import cache_delete

    _l1_del(_CHANNEL_BLACKLIST_CACHE_KEY)
    await cache_delete(_CHANNEL_BLACKLIST_CACHE_KEY)
    return True


async def remove_channel_blacklist(channel: str) -> bool:
    key = normalize_channel_key(channel)
    pool = await get_db()
    deleted = await pool.fetchval(
        "DELETE FROM yt_channel_blacklist WHERE channel_key = $1 RETURNING channel_key",
        key,
    )
    if deleted is not None:
        from services.cache_service import cache_delete

        _l1_del(_CHANNEL_BLACKLIST_CACHE_KEY)
        await cache_delete(_CHANNEL_BLACKLIST_CACHE_KEY)
        return True
    return False


async def list_channel_blacklist():
    pool = await get_db()
    return await pool.fetch(
        """
        SELECT channel_key, display_name, added_at
        FROM yt_channel_blacklist
        ORDER BY added_at DESC
        """
    )


async def get_all_channel_blacklist_keys() -> list[str]:
    local = _l1_get(_CHANNEL_BLACKLIST_CACHE_KEY)
    if local is not None:
        return local

    from services.cache_service import cache_get, cache_set

    cached = await cache_get(_CHANNEL_BLACKLIST_CACHE_KEY)
    if isinstance(cached, list):
        _l1_set(_CHANNEL_BLACKLIST_CACHE_KEY, cached)
        return cached

    pool = await get_db()
    rows = await pool.fetch("SELECT channel_key FROM yt_channel_blacklist")
    keys = [row["channel_key"] for row in rows]
    _l1_set(_CHANNEL_BLACKLIST_CACHE_KEY, keys)
    await cache_set(_CHANNEL_BLACKLIST_CACHE_KEY, keys, ttl_sec=300)
    return keys


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
            if bl == norm or (norm and len(bl) >= 4 and bl in norm):
                return True
            if bl == compact or (compact and len(bl) >= 4 and bl in compact):
                return True
    return False


async def add_blocked_word(word: str) -> bool:
    w = word.strip().lower()
    if len(w) < 2:
        return False
    pool = await get_db()
    await pool.execute(
        """
        INSERT INTO yt_blocked_words (word, added_at)
        VALUES ($1, $2)
        ON CONFLICT (word) DO NOTHING
        """,
        w,
        get_tehran_now_full(),
    )
    from services.cache_service import cache_delete

    _l1_del(_BLOCKED_WORDS_CACHE_KEY)
    await cache_delete(_BLOCKED_WORDS_CACHE_KEY)
    return True


async def remove_blocked_word(word: str) -> bool:
    w = word.strip().lower()
    pool = await get_db()
    deleted = await pool.fetchval(
        "DELETE FROM yt_blocked_words WHERE word = $1 RETURNING word",
        w,
    )
    if deleted is not None:
        from services.cache_service import cache_delete

        _l1_del(_BLOCKED_WORDS_CACHE_KEY)
        await cache_delete(_BLOCKED_WORDS_CACHE_KEY)
        return True
    return False


async def list_blocked_words():
    pool = await get_db()
    return await pool.fetch(
        "SELECT word, added_at FROM yt_blocked_words ORDER BY word ASC"
    )


async def get_all_blocked_words() -> list[str]:
    local = _l1_get(_BLOCKED_WORDS_CACHE_KEY)
    if local is not None:
        return local

    from services.cache_service import cache_get, cache_set

    cached = await cache_get(_BLOCKED_WORDS_CACHE_KEY)
    if isinstance(cached, list):
        _l1_set(_BLOCKED_WORDS_CACHE_KEY, cached)
        return cached

    pool = await get_db()
    rows = await pool.fetch("SELECT word FROM yt_blocked_words")
    words = [row["word"] for row in rows]
    _l1_set(_BLOCKED_WORDS_CACHE_KEY, words)
    await cache_set(_BLOCKED_WORDS_CACHE_KEY, words, ttl_sec=300)
    return words


async def seed_default_blocked_words(default_words: list[str]):
    now = get_tehran_now_full()
    records = [
        (word.strip().lower(), now)
        for word in default_words
        if len(word.strip()) >= 2
    ]
    if not records:
        return
    pool = await get_db()
    await pool.executemany(
        """
        INSERT INTO yt_blocked_words (word, added_at)
        VALUES ($1, $2)
        ON CONFLICT (word) DO NOTHING
        """,
        records,
    )
    from services.cache_service import cache_delete

    _l1_del(_BLOCKED_WORDS_CACHE_KEY)
    await cache_delete(_BLOCKED_WORDS_CACHE_KEY)
