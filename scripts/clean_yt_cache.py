#!/usr/bin/env python3
"""Remove ناشناس / incomplete rows from youtube_cache. Run from project root."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import init_db
from core.database.youtube import (
    drop_legacy_user_youtube_archive_table,
    count_incomplete_cache_rows,
    purge_incomplete_youtube_cache,
    purge_all_youtube_cache,
)


async def main():
    wipe_all = "--all" in sys.argv
    await init_db()
    await drop_legacy_user_youtube_archive_table()
    print("Dropped legacy table user_youtube_archive (if existed).")

    if wipe_all:
        n = await purge_all_youtube_cache()
        print(f"Deleted ALL youtube_cache rows: {n}")
        return

    before = await count_incomplete_cache_rows()
    print(f"Incomplete/ناشناس rows to delete: {before}")
    removed = await purge_incomplete_youtube_cache()
    after = await count_incomplete_cache_rows()
    print(f"Deleted: {removed}, remaining incomplete: {after}")


if __name__ == "__main__":
    asyncio.run(main())
