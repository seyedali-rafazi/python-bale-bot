from .base import get_connection
from .utils import get_tehran_now_full, get_tehran_today


def add_user(user_id, username):
    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_vip = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()


def get_user_info(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, is_vip, join_date, vip_expire_date FROM users WHERE user_id = ?",
        (user_id,),
    )
    result = cursor.fetchone()
    conn.close()
    return result


def get_total_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


def reset_user_limits(user_id):
    conn = get_connection()
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
