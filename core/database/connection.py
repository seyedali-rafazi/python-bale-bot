# core/database/connection.py

import aiosqlite
from .base import DB_NAME

_connection = None


async def get_db():
    global _connection
    if _connection is None:
        _connection = await aiosqlite.connect(DB_NAME)
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL;")
        await _connection.execute("PRAGMA synchronous=NORMAL;")
        await _connection.execute("PRAGMA temp_store=MEMORY;")
    return _connection


async def close_db():
    global _connection
    if _connection is not None:
        try:
            await _connection.close()
        except Exception:
            pass
        _connection = None
