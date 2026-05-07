from .base import get_connection
from .utils import get_tehran_today


def get_pinterest_downloads(user_id):
    conn = get_connection()
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
    conn = get_connection()
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
