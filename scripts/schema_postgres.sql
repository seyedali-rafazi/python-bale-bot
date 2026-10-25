-- schema_postgres.sql
-- اسکریپت ساخت تمام جداول و ایندکس‌های PostgreSQL برای ربات بله

-- 1. جدول کاربران
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
    cloud_total_mb INTEGER DEFAULT 0,
    cloud_used_mb INTEGER DEFAULT 0,
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

-- 2. جدول کش یوتیوب (شناسه عددی id معادل rowid در SQLite است)
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

-- 3. جدول اکسپلور اینستاگرام
CREATE TABLE IF NOT EXISTS instagram_explore (
    id SERIAL PRIMARY KEY,
    file_id TEXT UNIQUE
);

-- 4. جدول تراکنش‌ها
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    amount INTEGER,
    payload TEXT,
    provider_charge_id TEXT,
    date TEXT
);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);

-- 5. جدول تنظیمات
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- 6. جدول فایل‌های ابری
CREATE TABLE IF NOT EXISTS cloud_files (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    file_name TEXT,
    file_size_mb INTEGER,
    download_link TEXT,
    upload_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_cloud_files_user ON cloud_files(user_id);

-- 7. جدول آمار استفاده
CREATE TABLE IF NOT EXISTS usage_stats (
    user_id TEXT,
    action TEXT,
    date TEXT,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, action, date)
);

-- 8. جدول مانیتورینگ ایونت‌ها
CREATE TABLE IF NOT EXISTS monitoring_events (
    id SERIAL PRIMARY KEY,
    section TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'upload_success',
    user_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_created_at ON monitoring_events(created_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_section ON monitoring_events(section, created_at);

-- 9. لیست سیاه کانال‌های یوتیوب
CREATE TABLE IF NOT EXISTS yt_channel_blacklist (
    channel_key TEXT PRIMARY KEY,
    display_name TEXT,
    added_at TEXT
);

-- 10. کلمات مسدود شده یوتیوب
CREATE TABLE IF NOT EXISTS yt_blocked_words (
    word TEXT PRIMARY KEY,
    added_at TEXT
);
