# core/database/connection.py

import asyncio
import logging
from typing import Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from .base import PG_COMMAND_TIMEOUT, PG_POOL_MAX, PG_POOL_MIN, get_pg_dsn

logger = logging.getLogger(__name__)

_pool: Optional["asyncpg.Pool"] = None
_pool_lock = asyncio.Lock()


async def get_db():
    """Return the shared asyncpg connection pool, initializing it on first use."""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                if asyncpg is None:
                    raise RuntimeError(
                        "asyncpg is not installed. Run: pip install asyncpg"
                    )
                dsn = get_pg_dsn()
                _pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=PG_POOL_MIN,
                    max_size=PG_POOL_MAX,
                    command_timeout=PG_COMMAND_TIMEOUT,
                )
                logger.info(
                    "✅ PostgreSQL connection pool initialized (min=%s, max=%s)",
                    PG_POOL_MIN,
                    PG_POOL_MAX,
                )
    return _pool


get_pool = get_db


async def close_db():
    """Gracefully close the PostgreSQL connection pool."""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            pool = _pool
            _pool = None
            try:
                await asyncio.wait_for(pool.close(), timeout=10.0)
                logger.info("✅ PostgreSQL pool closed gracefully")
            except asyncio.TimeoutError:
                pool.terminate()
                logger.warning("⚠️ PostgreSQL pool close timed out; terminated")
            except Exception as e:
                logger.warning("Error while closing PostgreSQL pool: %s", e)
