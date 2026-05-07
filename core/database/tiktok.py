# core/database/tiktok.py

from .base import get_connection
from .utils import get_tehran_today


def get_tt_downloads(user_id):
    conn = get_connection()
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
    conn = get_connection()
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
    conn = get_connection()
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
    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO tiktok_explore (file_id) VALUES (?)", (file_id,)
    )
    conn.commit()
    conn.close()


def get_random_tiktok_explore_videos(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT file_id FROM tiktok_explore ORDER BY RANDOM() LIMIT ?", (limit,)
    )
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results


def delete_invalid_video_from_db(file_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tiktok_explore WHERE file_id = ?", (file_id,))
    conn.commit()
    conn.close()
