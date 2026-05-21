#!/usr/bin/env python3
"""One-shot: fill channel/title for old youtube_cache rows. Run from project root."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import init_db
from core.database.youtube import (
    count_cache_needing_metadata,
    backfill_youtube_cache_metadata,
    count_cache_missing_upload_date,
    backfill_cache_upload_dates,
)


async def main():
    await init_db()
    pending = await count_cache_needing_metadata()
    print(f"Rows needing metadata: {pending}")
    if pending == 0:
        return

    total_fixed = 0
    while True:
        remaining = await count_cache_needing_metadata()
        if remaining == 0:
            break
        print(f"Remaining: {remaining} ...")
        result = await backfill_youtube_cache_metadata(
            batch_size=50,
            max_total=200,
            delay_sec=0.4,
        )
        total_fixed += result["fixed"]
        print(f"  batch: {result}")
        if result["fixed"] == 0:
            print("No progress this batch; stopping.")
            break

    left = await count_cache_needing_metadata()
    print(f"Metadata done. Fixed ~{total_fixed}, still pending: {left}")

    missing_dates = await count_cache_missing_upload_date()
    print(f"Rows missing upload date (for channel sort): {missing_dates}")
    if missing_dates == 0:
        return

    date_fixed = 0
    while True:
        remaining = await count_cache_missing_upload_date()
        if remaining == 0:
            break
        print(f"Upload dates remaining: {remaining} ...")
        result = await backfill_cache_upload_dates(
            batch_size=50,
            max_total=200,
            delay_sec=0.35,
        )
        date_fixed += result["fixed"]
        print(f"  batch: {result}")
        if result["fixed"] == 0:
            print("No upload-date progress; stopping.")
            break

    left_dates = await count_cache_missing_upload_date()
    print(f"Upload dates done. Fixed ~{date_fixed}, still missing: {left_dates}")


if __name__ == "__main__":
    asyncio.run(main())
