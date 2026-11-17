# core/database/settings.py

from .connection import get_db


async def get_setting(key: str, default=None):
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT value FROM settings WHERE key = $1",
        key,
    )
    return val if val is not None else default


async def set_setting(key: str, value) -> None:
    pool = await get_db()
    await pool.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        key,
        str(value),
    )
