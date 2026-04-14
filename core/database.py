import sqlite3
from datetime import datetime

DB_NAME = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جدول کاربران
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0,
            join_date TEXT
        )
    ''')
    # جدول آمار استفاده روزانه
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_stats (
            user_id TEXT,
            action TEXT,
            date TEXT,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, action, date)
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id, username=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, username, today))
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

def log_usage(user_id, action):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute('''
        INSERT INTO usage_stats (user_id, action, date, count) 
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, action, date) 
        DO UPDATE SET count = count + 1
    ''', (user_id, action, today))
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
    cursor.execute("SELECT count FROM usage_stats WHERE user_id = ? AND action = ? AND date = ?", (user_id, action, today))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0
