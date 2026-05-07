# core/database/github.py

from .base import get_connection
from .utils import get_tehran_today


def get_gh_downloads(user_id):
    conn = get_connection()
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
    conn = get_connection()
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
