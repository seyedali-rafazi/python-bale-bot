# core/database/init_db.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم


async def init_db():
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    # PRAGMA journal_mode=WAL; در get_db() اجرا می‌شود، پس نیازی به تکرار نیست.

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
        await conn.execute("ALTER TABLE users ADD COLUMN yt_count INTEGER DEFAULT 0")
    if "yt_date" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN yt_date TEXT")
    if "music_count" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN music_count INTEGER DEFAULT 0")
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
        await conn.execute("ALTER TABLE users ADD COLUMN tt_dl_count INTEGER DEFAULT 0")
    if "tt_dl_date" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN tt_dl_date TEXT")
    if "ig_dl_count" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN ig_dl_count INTEGER DEFAULT 0")
    if "ig_dl_date" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN ig_dl_date TEXT")
    if "ig_exp_count" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN ig_exp_count INTEGER DEFAULT 0"
        )
    if "ig_exp_date" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN ig_exp_date TEXT")
    if "gh_count" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN gh_count INTEGER DEFAULT 0")
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
    if "cloud_total_mb" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN cloud_total_mb INTEGER DEFAULT 0"
        )
    if "cloud_used_mb" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN cloud_used_mb INTEGER DEFAULT 0"
        )
    if "web_search_dl_count" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN web_search_dl_count INTEGER DEFAULT 0"
        )
    if "web_search_dl_date" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN web_search_dl_date TEXT"
        )
    if "tg_count" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN tg_count INTEGER DEFAULT 0")
    if "tg_date" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN tg_date TEXT")

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
    if "title" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN title TEXT DEFAULT 'بدون عنوان'"
        )
    if "channel_name" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN channel_name TEXT"
        )
    if "yt_video_id" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN yt_video_id TEXT"
        )
    if "format_type" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN format_type TEXT DEFAULT 'video_zip'"
        )
    if "quality" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN quality TEXT DEFAULT '480'"
        )
    if "cached_at" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN cached_at TEXT"
        )
    if "uploaded_at" not in yt_cache_columns:
        await conn.execute(
            "ALTER TABLE youtube_cache ADD COLUMN uploaded_at TEXT"
        )

    if "arc_fetch_count" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN arc_fetch_count INTEGER DEFAULT 0"
        )
    if "arc_fetch_date" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN arc_fetch_date TEXT"
        )
    if "ai_chat_count" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN ai_chat_count INTEGER DEFAULT 0"
        )
    if "ai_chat_date" not in columns:
        await conn.execute(
            "ALTER TABLE users ADD COLUMN ai_chat_date TEXT"
        )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS instagram_explore (
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
        CREATE TABLE IF NOT EXISTS cloud_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            file_name TEXT,
            file_size_mb INTEGER,
            download_link TEXT,
            upload_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
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

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'upload_success',
            user_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_monitoring_events_created_at
        ON monitoring_events(created_at)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_monitoring_events_section
        ON monitoring_events(section, created_at)
    """)

    await conn.execute("DROP TABLE IF EXISTS user_youtube_archive")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS yt_channel_blacklist (
            channel_key TEXT PRIMARY KEY,
            display_name TEXT,
            added_at TEXT
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS yt_blocked_words (
            word TEXT PRIMARY KEY,
            added_at TEXT
        )
    """)

    from core.yt_moderation import get_default_blocked_words_seed
    from .yt_blacklist import seed_default_blocked_words

    await seed_default_blocked_words(get_default_blocked_words_seed())

    await conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('youtube_enabled', '1')"
    )
    await conn.commit()
