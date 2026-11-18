# services/flaresolverr.py
"""
FlareSolverr integration service to bypass Cloudflare protection.
Repo: https://github.com/Flaresolverr/Flaresolverr
"""

import asyncio
import os
import json
import logging
import time
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from services.http_client import get_http_session

load_dotenv()

logger = logging.getLogger(__name__)

# Default FlareSolverr URL (can be configured in .env via FLARESOLVERR_URL)
DEFAULT_FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://localhost:8191/v1")
_FLARESOLVERR_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("FLARESOLVERR_MAX_CONCURRENT", "2"))))
_FLARESOLVERR_COOLDOWN_SEC = max(5.0, float(os.getenv("FLARESOLVERR_COOLDOWN_SEC", "30")))
_flaresolverr_down_until = 0.0


async def flaresolverr_request(
    url: str,
    method: str = "GET",
    post_data: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 60,
    flaresolverr_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Send a request through FlareSolverr to bypass Cloudflare challenges.

    Returns the solution dict containing 'status', 'response', 'cookies', 'userAgent',
    or None if FlareSolverr is not reachable or fails to solve the challenge.
    """
    global _flaresolverr_down_until
    if time.monotonic() < _flaresolverr_down_until:
        return None

    fs_url = (flaresolverr_url or DEFAULT_FLARESOLVERR_URL).rstrip("/")
    if not fs_url.endswith("/v1"):
        fs_url += "/v1"

    cmd = "request.post" if method.upper() == "POST" else "request.get"
    payload: Dict[str, Any] = {
        "cmd": cmd,
        "url": url,
        "maxTimeout": timeout * 1000,
    }

    if method.upper() == "POST" and post_data:
        payload["postData"] = post_data

    if headers:
        payload["headers"] = headers

    try:
        async with _FLARESOLVERR_SEMAPHORE:
            if time.monotonic() < _flaresolverr_down_until:
                return None
            session = await get_http_session()
            async with session.post(fs_url, json=payload, timeout=timeout + 5) as resp:
                if resp.status != 200:
                    logger.warning(
                        "[FlareSolverr] HTTP status %s from FlareSolverr at %s",
                        resp.status,
                        fs_url,
                    )
                    return None

                data = await resp.json()
                if data.get("status") == "ok":
                    _flaresolverr_down_until = 0.0
                    logger.info(
                        "[FlareSolverr] Successfully solved Cloudflare challenge for %s", url
                    )
                    return data.get("solution")
                else:
                    logger.warning(
                        "[FlareSolverr] Failed to solve challenge for %s: %s",
                        url,
                        data.get("message"),
                    )
                    return None

    except Exception as e:
        _flaresolverr_down_until = time.monotonic() + _FLARESOLVERR_COOLDOWN_SEC
        logger.warning(
            "[FlareSolverr] Could not connect to FlareSolverr at %s: %s (cooling down %.0fs)",
            fs_url,
            e,
            _FLARESOLVERR_COOLDOWN_SEC,
        )
        return None
