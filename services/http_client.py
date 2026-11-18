# services/http_client.py

import asyncio
import aiohttp
from typing import Optional

_http_session: Optional[aiohttp.ClientSession] = None
_http_session_lock = asyncio.Lock()


async def init_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        async with _http_session_lock:
            if _http_session is None or _http_session.closed:
                timeout = aiohttp.ClientTimeout(total=30, sock_connect=10)
                connector = aiohttp.TCPConnector(
                    limit=100,
                    limit_per_host=24,
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                )
                _http_session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector,
                    max_line_size=65536,
                    max_field_size=65536,
                )
    return _http_session


async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        return await init_http_session()
    return _http_session


async def close_http_session() -> None:
    global _http_session
    async with _http_session_lock:
        if _http_session is not None and not _http_session.closed:
            await _http_session.close()
            _http_session = None
