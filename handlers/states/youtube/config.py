import asyncio
import os

MAX_NORMAL_DOWNLOADS = max(1, int(os.getenv("YT_MAX_NORMAL_DOWNLOADS", "3")))
MAX_VIP_DOWNLOADS = max(1, int(os.getenv("YT_MAX_VIP_DOWNLOADS", "6")))

telegram_normal_semaphore = asyncio.Semaphore(MAX_NORMAL_DOWNLOADS)
telegram_vip_semaphore = asyncio.Semaphore(MAX_VIP_DOWNLOADS)
server_normal_semaphore = asyncio.Semaphore(MAX_NORMAL_DOWNLOADS)
server_vip_semaphore = asyncio.Semaphore(MAX_VIP_DOWNLOADS)

STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL_ID", "@digiyt")
