# core/database.py

import sqlite3
from datetime import datetime, timedelta
import pytz
import json

DB_NAME = "bot_data.db"
TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def get_tehran_today():
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")


def get_tehran_now_full():
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0,
            join_date TEXT
        )
    """)

    # اضافه کردن ستون‌های جدید با ALTER TABLE
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

    # --- ستون‌های جدید برای پینترست ---
    if "pinterest_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN pinterest_count INTEGER DEFAULT 0")
    if "pinterest_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN pinterest_date TEXT")

    # --- ستون‌های جدید برای تیکتاک ---
    if "tt_dl_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_dl_count INTEGER DEFAULT 0")
    if "tt_dl_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_dl_date TEXT")
    if "tt_exp_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_exp_count INTEGER DEFAULT 0")
    if "tt_exp_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN tt_exp_date TEXT")

    # --- ستون‌های جدید برای گیتهاب ---
    if "gh_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN gh_count INTEGER DEFAULT 0")
    if "gh_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN gh_date TEXT")

    # جدول کش کردن ویدیوهای یوتیوب
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS youtube_cache (
            video_id TEXT PRIMARY KEY,
            file_ids TEXT
        )
    """)

    # --- بخش جدید: اضافه کردن ستون view_count بدون حذف داده‌های قبلی ---
    cursor.execute("PRAGMA table_info(youtube_cache)")
    yt_cache_columns = [column[1] for column in cursor.fetchall()]
    if "view_count" not in yt_cache_columns:
        cursor.execute(
            "ALTER TABLE youtube_cache ADD COLUMN view_count INTEGER DEFAULT 0"
        )

    # جدول جدید برای ذخیره ویدیوهای اکسپلور تیک‌تاک
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiktok_explore (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE
        )
    """)

    # جدول تراکنش‌ها
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

    # جدول تنظیمات
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


# ----------- بخش تنظیمات ربات -----------


def get_setting(key, default=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else default


def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value))
    )
    conn.commit()
    conn.close()


# ----------- بخش مربوط به تراکنش ها -----------


def add_transaction(user_id, amount, payload, provider_charge_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    current_time = get_tehran_now_full()
    cursor.execute(
        """
        INSERT INTO transactions (user_id, amount, payload, provider_charge_id, date)
        VALUES (?, ?, ?, ?, ?)
    """,
        (str(user_id), amount, payload, provider_charge_id, current_time),
    )
    conn.commit()
    conn.close()


def is_vip(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_vip, vip_expire_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()

    if not result:
        conn.close()
        return False

    vip_status, expire_date_str = result

    if vip_status == 1:
        if expire_date_str:
            expire_date = datetime.fromisoformat(expire_date_str)
            if datetime.now() > expire_date:
                cursor.execute(
                    "UPDATE users SET is_vip = 0, vip_expire_date = NULL WHERE user_id = ?",
                    (user_id,),
                )
                conn.commit()
                conn.close()
                return False
        conn.close()
        return True

    conn.close()
    return False


def add_vip_time(user_id, days: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT is_vip, vip_expire_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()

    now = datetime.now()
    if result and result[0] == 1 and result[1]:
        current_expire = datetime.fromisoformat(result[1])
        if current_expire > now:
            new_expire = current_expire + timedelta(days=days)
        else:
            new_expire = now + timedelta(days=days)
    else:
        new_expire = now + timedelta(days=days)

    expire_date_str = new_expire.isoformat()
    cursor.execute(
        "UPDATE users SET is_vip = 1, vip_expire_date = ? WHERE user_id = ?",
        (expire_date_str, user_id),
    )
    conn.commit()
    conn.close()


def get_total_vip_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE is_vip = 1 AND (vip_expire_date IS NULL OR vip_expire_date > ?)",
        (now_str,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ----------- بخش مربوط به دانلودهای موسیقی -----------


def get_music_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute(
        "SELECT music_count, music_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()
    conn.close()

    if result:
        count, db_date = result
        if db_date != today:
            return 0
        return count
    return 0


def increment_music_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute(
        "SELECT music_count, music_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()

    if result:
        count, db_date = result
        if db_date != today:
            new_count = 1
        else:
            new_count = count + 1
        cursor.execute(
            "UPDATE users SET music_count = ?, music_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )

    conn.commit()
    conn.close()


def add_user(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    join_date = get_tehran_now_full()
    today = get_tehran_today()

    cursor.execute(
        """
        INSERT OR IGNORE INTO users (user_id, username, is_vip, join_date, yt_count, yt_date, pinterest_count, pinterest_date) 
        VALUES (?, ?, 0, ?, 0, ?, 0, ?)
    """,
        (user_id, username, join_date, today, today),
    )

    conn.commit()
    conn.close()


def set_vip(user_id, status: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_vip = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()


def get_user_info(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, is_vip, join_date, vip_expire_date FROM users WHERE user_id = ?",
        (user_id,),
    )
    result = cursor.fetchone()
    conn.close()
    return result


# ----------- بخش مربوط به دانلودهای یوتیوب -----------


def get_yt_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute("SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        count, db_date = result
        if db_date != today:
            return 0
        return count
    return 0


def increment_yt_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute("SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        count, db_date = result
        if db_date != today:
            new_count = 1
        else:
            new_count = count + 1
        cursor.execute(
            "UPDATE users SET yt_count = ?, yt_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )

    conn.commit()
    conn.close()


def decrement_yt_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute("SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        count, db_date = result
        if db_date == today and count > 0:
            new_count = count - 1
            cursor.execute(
                "UPDATE users SET yt_count = ? WHERE user_id = ?",
                (new_count, user_id),
            )

    conn.commit()
    conn.close()


# ----------- بخش مربوط به پینترست -----------


def get_pinterest_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute(
        "SELECT pinterest_count, pinterest_date FROM users WHERE user_id = ?",
        (user_id,),
    )
    result = cursor.fetchone()
    conn.close()

    if result:
        count, db_date = result
        if db_date != today:
            return 0
        return count
    return 0


def increment_pinterest_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute(
        "SELECT pinterest_count, pinterest_date FROM users WHERE user_id = ?",
        (user_id,),
    )
    result = cursor.fetchone()

    if result:
        count, db_date = result
        if db_date != today:
            new_count = 1
        else:
            new_count = count + 1
        cursor.execute(
            "UPDATE users SET pinterest_count = ?, pinterest_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )

    conn.commit()
    conn.close()


# -----------------------------------------------------


def log_usage(user_id, action):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    try:
        cursor.execute(
            """
            INSERT INTO usage_stats (user_id, action, date, count) 
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, action, date) 
            DO UPDATE SET count = count + 1
        """,
            (user_id, action, today),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def get_total_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_user_usage_today(user_id, action):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    try:
        cursor.execute(
            "SELECT count FROM usage_stats WHERE user_id = ? AND action = ? AND date = ?",
            (user_id, action, today),
        )
        result = cursor.fetchone()
    except sqlite3.OperationalError:
        result = None
    finally:
        conn.close()
    return result[0] if result else 0


def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


# ----------- بخش جدید: کش (Cache) یوتیوب -----------


def get_cached_video(video_id: str) -> list:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_ids FROM youtube_cache WHERE video_id = ?", (video_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        return json.loads(result[0])
    return []


def save_cached_video(video_id: str, file_ids: list):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    file_ids_json = json.dumps(file_ids)
    cursor.execute(
        "INSERT OR REPLACE INTO youtube_cache (video_id, file_ids) VALUES (?, ?)",
        (video_id, file_ids_json),
    )
    conn.commit()
    conn.close()


def increment_yt_video_view(video_id: str):
    """افزایش تعداد بازدید یک ویدیوی کش شده"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE youtube_cache SET view_count = view_count + 1 WHERE video_id = ?",
        (video_id,),
    )
    conn.commit()
    conn.close()


def get_top_cached_videos(limit=10):
    """دریافت ویدیوهای پر بازدید کش شده"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # برای دسترسی به ستون‌ها با اسم (مثل دیکشنری)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT video_id, file_ids, view_count FROM youtube_cache ORDER BY view_count DESC LIMIT ?",
        (limit,),
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ----------- بخش جدید: تیک تاک -----------


def get_tt_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    cursor.execute(
        "SELECT tt_dl_count, tt_dl_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        count, db_date = result
        if db_date != today:
            return 0
        return count
    return 0


def increment_tt_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    cursor.execute(
        "SELECT tt_dl_count, tt_dl_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()
    if result:
        count, db_date = result
        new_count = 1 if db_date != today else count + 1
        cursor.execute(
            "UPDATE users SET tt_dl_count = ?, tt_dl_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    conn.commit()
    conn.close()


def get_tt_explores(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    cursor.execute(
        "SELECT tt_exp_count, tt_exp_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        count, db_date = result
        if db_date != today:
            return 0
        return count
    return 0


def increment_tt_explores(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    cursor.execute(
        "SELECT tt_exp_count, tt_exp_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()
    if result:
        count, db_date = result
        new_count = 1 if db_date != today else count + 1
        cursor.execute(
            "UPDATE users SET tt_exp_count = ?, tt_exp_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    conn.commit()
    conn.close()


def add_tiktok_explore_video(file_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO tiktok_explore (file_id) VALUES (?)", (file_id,)
    )
    conn.commit()
    conn.close()


def get_random_tiktok_explore_videos(limit=5):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT file_id FROM tiktok_explore ORDER BY RANDOM() LIMIT ?", (limit,)
    )
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results


def delete_invalid_video_from_db(file_id: str):
    """
    حذف ویدیوهای منقضی شده یا نامعتبر از دیتابیس اکسپلور تیک‌تاک
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tiktok_explore WHERE file_id = ?", (file_id,))
    conn.commit()
    conn.close()


# توابع گیتهاب
def get_gh_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    cursor.execute("SELECT gh_count, gh_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        count, db_date = result
        return count if db_date == today else 0
    return 0


def increment_gh_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()
    cursor.execute("SELECT gh_count, gh_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        count, db_date = result
        new_count = 1 if db_date != today else count + 1
        cursor.execute(
            "UPDATE users SET gh_count = ?, gh_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    conn.commit()
    conn.close()


def reset_user_limits(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users 
        SET yt_count = 0, music_count = 0, pinterest_count = 0, tt_dl_count = 0, tt_exp_count = 0
        WHERE user_id = ?
        """,
        (user_id,),
    )
    conn.commit()
    conn.close()


def add_vip_time_to_all(days: int) -> int:
    """اضافه کردن زمان مشخص به تمام کاربران VIP فعال"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, vip_expire_date FROM users WHERE is_vip = 1")
    vip_users = cursor.fetchall()

    now = datetime.now()
    updated_count = 0

    for user_id, expire_str in vip_users:
        if expire_str:
            current_expire = datetime.fromisoformat(expire_str)
            # فقط به کسانی که اشتراکشون هنوز منقضی نشده اضافه میکنیم
            if current_expire > now:
                new_expire = current_expire + timedelta(days=days)
                cursor.execute(
                    "UPDATE users SET vip_expire_date = ? WHERE user_id = ?",
                    (new_expire.isoformat(), user_id),
                )
                updated_count += 1

    conn.commit()
    conn.close()
    return updated_count
