# services/chromium_workload.py
"""
Pinterest (Playwright Chromium) and web «دانلود صفحه» (single-file → Chromium)
do not share one Python object, but they compete on the same machine:
RAM, CPU, and often /dev/shm in Docker/Linux.

When web search runs several SingleFile jobs at once, Pinterest can start failing
(timeouts, empty HTML, no images) even though the features are unrelated in code.

Use one asyncio semaphore so total concurrent «heavy Chromium» work stays bounded.
Override with env: HEAVY_CHROMIUM_MAX_CONCURRENT (default 2).
"""

import asyncio
import os

_DEFAULT_MAX = 2
_max = max(1, int(os.getenv("HEAVY_CHROMIUM_MAX_CONCURRENT", str(_DEFAULT_MAX))))

heavy_chromium_semaphore = asyncio.Semaphore(_max)
