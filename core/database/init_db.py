# core/database/init_db.py

import logging
from pathlib import Path

from .connection import get_db

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "schema_postgres.sql"

_FALLBACK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    is_vip INTEGER DEFAULT 0,
    join_date TEXT,
    yt_count INTEGER DEFAULT 0,
    yt_date TEXT,
    music_count INTEGER DEFAULT 0,
    music_date TEXT,
    vip_expire_date TEXT,
    pinterest_count INTEGER DEFAULT 0,
    pinterest_date TEXT,
    tt_dl_count INTEGER DEFAULT 0,
    tt_dl_date TEXT,
    ig_dl_count INTEGER DEFAULT 0,
    ig_dl_date TEXT,
    ig_exp_count INTEGER DEFAULT 0,
    ig_exp_date TEXT,
    gh_count INTEGER DEFAULT 0,
    gh_date TEXT,
    citation_count INTEGER DEFAULT 0,
    book_download_count INTEGER DEFAULT 0,
    cloud_total_mb DOUBLE PRECISION DEFAULT 0,
    cloud_used_mb DOUBLE PRECISION DEFAULT 0,
    web_search_dl_count INTEGER DEFAULT 0,
    web_search_dl_date TEXT,
    tg_count INTEGER DEFAULT 0,
    tg_date TEXT,
    kaggle_count INTEGER DEFAULT 0,
    kaggle_date TEXT,
    arc_fetch_count INTEGER DEFAULT 0,
    arc_fetch_date TEXT,
    ai_chat_count INTEGER DEFAULT 0,
    ai_chat_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_vip_expire
    ON users(vip_expire_date)
    WHERE is_vip = 1;
CREATE TABLE IF NOT EXISTS youtube_cache (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT UNIQUE NOT NULL,
    file_ids TEXT,
    view_count INTEGER DEFAULT 0,
    title TEXT DEFAULT 'بدون عنوان',
    channel_name TEXT,
    yt_video_id TEXT,
    format_type TEXT DEFAULT 'video_zip',
    quality TEXT DEFAULT '480',
    cached_at TEXT,
    uploaded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_yt_cache_channel ON youtube_cache(channel_name);
CREATE INDEX IF NOT EXISTS idx_yt_cache_yt_id ON youtube_cache(yt_video_id);
CREATE INDEX IF NOT EXISTS idx_yt_cache_views ON youtube_cache(view_count DESC);
CREATE INDEX IF NOT EXISTS idx_yt_cache_uploaded ON youtube_cache(uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_cache_id_desc ON youtube_cache(id DESC);
CREATE INDEX IF NOT EXISTS idx_yt_cache_archive_channel_has_files
    ON youtube_cache(channel_name, uploaded_at DESC, id DESC)
    WHERE file_ids IS NOT NULL AND file_ids != '[]';
CREATE TABLE IF NOT EXISTS instagram_explore (
    id SERIAL PRIMARY KEY,
    file_id TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    amount INTEGER,
    payload TEXT,
    provider_charge_id TEXT,
    date TEXT
);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS cloud_files (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    file_name TEXT,
    file_size_mb DOUBLE PRECISION,
    download_link TEXT,
    upload_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_cloud_files_user ON cloud_files(user_id);
CREATE TABLE IF NOT EXISTS usage_stats (
    user_id TEXT,
    action TEXT,
    date TEXT,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, action, date)
);
CREATE TABLE IF NOT EXISTS monitoring_events (
    id SERIAL PRIMARY KEY,
    section TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'upload_success',
    user_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_created_at ON monitoring_events(created_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_section ON monitoring_events(section, created_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_created_user
    ON monitoring_events(created_at, user_id)
    WHERE user_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS yt_channel_blacklist (
    channel_key TEXT PRIMARY KEY,
    display_name TEXT,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS yt_blocked_words (
    word TEXT PRIMARY KEY,
    added_at TEXT
);
"""


async def _ensure_float_cloud_columns(conn) -> None:
    """Upgrade legacy INTEGER cloud size columns to DOUBLE PRECISION if needed."""
    checks = [
        ("users", "cloud_total_mb"),
        ("users", "cloud_used_mb"),
        ("cloud_files", "file_size_mb"),
    ]
    for table_name, col_name in checks:
        data_type = await conn.fetchval(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = $1
              AND column_name = $2
            """,
            table_name,
            col_name,
        )
        if data_type and data_type != "double precision":
            await conn.execute(
                f"ALTER TABLE {table_name} ALTER COLUMN {col_name} TYPE DOUBLE PRECISION"
            )


async def _ensure_trigram_indexes(conn) -> None:
    """Create pg_trgm GIN indexes for fast ILIKE '%...%' archive search when allowed."""
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_yt_cache_title_trgm ON youtube_cache USING gin (title gin_trgm_ops)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_yt_cache_channel_trgm ON youtube_cache USING gin (channel_name gin_trgm_ops)"
        )
    except Exception as e:
        logger.debug("Skipping pg_trgm index setup: %s", e)


async def init_db():
    pool = await get_db()
    schema_sql = (
        _SCHEMA_PATH.read_text(encoding="utf-8")
        if _SCHEMA_PATH.exists()
        else _FALLBACK_SCHEMA_SQL
    )

    async with pool.acquire() as conn:
        await conn.execute(schema_sql)
        await _ensure_float_cloud_columns(conn)
        await _ensure_trigram_indexes(conn)
        await conn.execute("DROP TABLE IF EXISTS user_youtube_archive")
        await conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ('youtube_enabled', '1')
            ON CONFLICT (key) DO NOTHING
            """
        )

    from core.yt_moderation import get_default_blocked_words_seed
    from .yt_blacklist import seed_default_blocked_words

    await seed_default_blocked_words(get_default_blocked_words_seed())
