from .base import get_connection


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0,
            join_date TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]

    if "yt_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN yt_count INTEGER DEFAULT 0")
    if "yt_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN yt_date TEXT")
    if "music_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN music_count INTEGER DEFAULT 0")
    if "music_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN music_date TEXT")
    if "vip_expire_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN vip_expire_date TEXT")
    if "pinterest_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN pinterest_count INTEGER DEFAULT 0")
    if "pinterest_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN pinterest_date TEXT")
    if "tt_dl_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_dl_count INTEGER DEFAULT 0")
    if "tt_dl_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_dl_date TEXT")
    if "tt_exp_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_exp_count INTEGER DEFAULT 0")
    if "tt_exp_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_exp_date TEXT")
    if "gh_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN gh_count INTEGER DEFAULT 0")
    if "gh_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN gh_date TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS youtube_cache (
            video_id TEXT PRIMARY KEY,
            file_ids TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(youtube_cache)")
    yt_cache_columns = [column[1] for column in cursor.fetchall()]
    if "view_count" not in yt_cache_columns:
        cursor.execute(
            "ALTER TABLE youtube_cache ADD COLUMN view_count INTEGER DEFAULT 0"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiktok_explore (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            amount INTEGER,
            payload TEXT,
            provider_charge_id TEXT,
            date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('youtube_enabled', '1')"
    )

    conn.commit()
    conn.close()
