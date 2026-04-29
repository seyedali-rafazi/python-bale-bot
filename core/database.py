# core/database.py


import sqlite3
from datetime import datetime
import pytz

DB_NAME = "bot_data.db"
TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def get_tehran_today():  # ## تغییر ##: ساخت یک تابع کمکی برای گرفتن تاریخ تهران
    """تاریخ امروز را بر اساس منطقه زمانی تهران برمی‌گرداند."""
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")


def get_tehran_now_full():  # ## تغییر ##: تابع کمکی برای تاریخ و زمان کامل
    """تاریخ و زمان کامل را بر اساس منطقه زمانی تهران برمی‌گرداند."""
    return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. ساخت جدول کاربران
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0,
            join_date TEXT
        )
    """)

    # --- آپدیت خودکار دیتابیس (Migration) ---
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]

    if "yt_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN yt_count INTEGER DEFAULT 0")
    if "yt_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN yt_date TEXT")

    # اضافه کردن خودکار ستون‌های مربوط به موزیک
    if "music_count" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN music_count INTEGER DEFAULT 0")
    if "music_date" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN music_date TEXT")
    # ----------------------------------------


# ----------- بخش مربوط به دانلودهای موسیقی -----------


def get_music_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

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
    today = datetime.now().strftime("%Y-%m-%d")

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
    join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        """
        INSERT OR IGNORE INTO users (user_id, username, is_vip, join_date, yt_count, yt_date) 
        VALUES (?, ?, 0, ?, 0, ?)
    """,
        (user_id, username, join_date, today),
    )

    conn.commit()
    conn.close()


def is_vip(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT is_vip FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False


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
        "SELECT username, is_vip, join_date FROM users WHERE user_id = ?", (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    return result


# ----------- بخش مربوط به دانلودهای یوتیوب -----------


def get_yt_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

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
    today = datetime.now().strftime("%Y-%m-%d")

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
    today = datetime.now().strftime("%Y-%m-%d")

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
    today = datetime.now().strftime("%Y-%m-%d")
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
