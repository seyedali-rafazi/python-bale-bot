# core/database/init_db.py

import aiosqlite
from .base import DB_NAME


async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                is_vip INTEGER DEFAULT 0,
                join_date TEXT
            )
        """)

        async with conn.execute("PRAGMA table_info(users)") as cursor:
            columns = [column[1] for column in await cursor.fetchall()]

        if "yt_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN yt_count INTEGER DEFAULT 0"
            )
        if "yt_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN yt_date TEXT")
        if "music_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN music_count INTEGER DEFAULT 0"
            )
        if "music_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN music_date TEXT")
        if "vip_expire_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN vip_expire_date TEXT")
        if "pinterest_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN pinterest_count INTEGER DEFAULT 0"
            )
        if "pinterest_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN pinterest_date TEXT")
        if "tt_dl_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN tt_dl_count INTEGER DEFAULT 0"
            )
        if "tt_dl_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN tt_dl_date TEXT")
        if "tt_exp_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN tt_exp_count INTEGER DEFAULT 0"
            )
        if "tt_exp_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN tt_exp_date TEXT")
        if "gh_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN gh_count INTEGER DEFAULT 0"
            )
        if "gh_date" not in columns:
            await conn.execute("ALTER TABLE users ADD COLUMN gh_date TEXT")
        if "citation_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN citation_count INTEGER DEFAULT 0"
            )
        if "book_download_count" not in columns:
            await conn.execute(
                "ALTER TABLE users ADD COLUMN book_download_count INTEGER DEFAULT 0"
            )

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS youtube_cache (
                video_id TEXT PRIMARY KEY,
                file_ids TEXT
            )
        """)

        async with conn.execute("PRAGMA table_info(youtube_cache)") as cursor:
            yt_cache_columns = [column[1] for column in await cursor.fetchall()]
        if "view_count" not in yt_cache_columns:
            await conn.execute(
                "ALTER TABLE youtube_cache ADD COLUMN view_count INTEGER DEFAULT 0"
            )

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_explore (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                amount INTEGER,
                payload TEXT,
                provider_charge_id TEXT,
                date TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats (
                user_id TEXT,
                action TEXT,
                date TEXT,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, action, date)
            )
        """)

        await conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('youtube_enabled', '1')"
        )
        await conn.commit()
