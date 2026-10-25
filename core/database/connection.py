# core/database/connection.py

import asyncio
import logging
import aiosqlite
from .base import DB_NAME

logger = logging.getLogger(__name__)

_connection: aiosqlite.Connection | None = None
_conn_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _connection
    if _connection is None:
        async with _conn_lock:
            if _connection is None:
                conn = await aiosqlite.connect(DB_NAME)
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                await conn.execute("PRAGMA temp_store=MEMORY;")
                _connection = conn
    return _connection


async def close_db():
    global _connection
    async with _conn_lock:
        if _connection is not None:
            conn = _connection
            _connection = None
            try:
                await conn.close()
                logger.info("✅ SQLite connection closed gracefully")
            except Exception as e:
                logger.warning("Error while closing SQLite connection: %s", e)

