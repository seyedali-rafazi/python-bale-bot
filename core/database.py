# core/database.py

import sqlite3
from datetime import datetime, timedelta
import pytz
import json  # <-- اضافه شده برای ذخیره لیست فایل‌ها

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

    # --- ستون جدید برای اشتراک ---
    if "vip_expire_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN vip_expire_date TEXT")

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

    # --- جدول جدید برای کش کردن ویدیوهای یوتیوب (هیچ آسیبی به داده‌های قبلی نمی‌زند) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS youtube_cache (
            video_id TEXT PRIMARY KEY,
            file_ids TEXT
        )
    """)

    conn.commit()
    conn.close()


# ----------- بخش مربوط به  تراکنش ها -----------


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
            # اگر منقضی شده بود
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
    """تمدید اشتراک (افزودن روز به تاریخ قبلی یا از همین لحظه)"""
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
            return 0  # روز جدید شده است
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
        INSERT OR IGNORE INTO users (user_id, username, is_vip, join_date, yt_count, yt_date) 
        VALUES (?, ?, 0, ?, 0, ?)
    """,
        (user_id, username, join_date, today),
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
            return 0  # اگر روز جدید شده، مصرف 0 در نظر گرفته می‌شود
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


# -----------------------------------------------------


def log_usage(user_id, action):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = get_tehran_today()

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
    cursor.execute(
        "SELECT count FROM usage_stats WHERE user_id = ? AND action = ? AND date = ?",
        (user_id, action, today),
    )
    result = cursor.fetchone()
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
    """
    آیدی یوتیوب را می‌گیرد و لیست file_id های موجود در کانال را برمی‌گرداند.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_ids FROM youtube_cache WHERE video_id = ?", (video_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        return json.loads(result[0])
    return []


def save_cached_video(video_id: str, file_ids: list):
    """
    آیدی یوتیوب و لیست file_id ها را به صورت JSON ذخیره می‌کند.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    file_ids_json = json.dumps(file_ids)

    # استفاده از INSERT OR REPLACE تا در صورت وجود آپدیت شود
    cursor.execute(
        "INSERT OR REPLACE INTO youtube_cache (video_id, file_ids) VALUES (?, ?)",
        (video_id, file_ids_json),
    )

    conn.commit()
    conn.close()
