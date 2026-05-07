# core/database/usage.py

import sqlite3
from .base import get_connection
from .utils import get_tehran_today


def log_usage(user_id, action):
    conn = get_connection()
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


def get_user_usage_today(user_id, action):
    conn = get_connection()
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
