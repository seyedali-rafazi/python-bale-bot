# core/database/settings.py

import time
from services.cache_service import cache_get, cache_set
from .connection import get_db

_SETTING_CACHE_TTL_SEC = 300
_L1_TTL_SEC = 60.0
_l1_settings: dict[str, tuple[object, float]] = {}


async def get_setting(key: str, default=None):
    l1 = _l1_settings.get(key)
    if l1 is not None:
        val, exp = l1
        if time.monotonic() < exp:
            return val if val is not None else default
        _l1_settings.pop(key, None)

    cache_key = f"setting:{key}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict) and "value" in cached:
        val = cached["value"]
        _l1_settings[key] = (val, time.monotonic() + _L1_TTL_SEC)
        return val if val is not None else default

    pool = await get_db()
    val = await pool.fetchval(
        "SELECT value FROM settings WHERE key = $1",
        key,
    )
    _l1_settings[key] = (val, time.monotonic() + _L1_TTL_SEC)
    await cache_set(cache_key, {"value": val}, ttl_sec=_SETTING_CACHE_TTL_SEC)
    return val if val is not None else default


async def set_setting(key: str, value) -> None:
    pool = await get_db()
    str_val = str(value)
    await pool.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        key,
        str_val,
    )
    _l1_settings[key] = (str_val, time.monotonic() + _L1_TTL_SEC)
    await cache_set(f"setting:{key}", {"value": str_val}, ttl_sec=_SETTING_CACHE_TTL_SEC)
