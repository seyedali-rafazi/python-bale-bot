#!/usr/bin/env python3
"""One-shot: fill channel/title for old youtube_cache rows. Run from project root."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import init_db, close_db
from core.database.youtube import (
    count_cache_needing_metadata,
    backfill_youtube_cache_metadata,
    count_cache_missing_upload_date,
    backfill_cache_upload_dates,
)


async def main():
    await init_db()
    try:
        pending = await count_cache_needing_metadata()
        print(f"Rows needing metadata: {pending}")
        if pending > 0:
            result = await backfill_youtube_cache_metadata(
                batch_size=50,
                max_total=None,
                delay_sec=0.4,
            )
            left = await count_cache_needing_metadata()
            print(f"Metadata done. Batch result: {result}, still pending: {left}")

        missing_dates = await count_cache_missing_upload_date()
        print(f"Rows missing upload date (for channel sort): {missing_dates}")
        if missing_dates == 0:
            return

        date_result = await backfill_cache_upload_dates(
            batch_size=50,
            max_total=None,
            delay_sec=0.35,
        )
        left_dates = await count_cache_missing_upload_date()
        print(f"Upload dates done. Batch result: {date_result}, still missing: {left_dates}")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
