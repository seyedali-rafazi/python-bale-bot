from datetime import datetime, timedelta
from .base import get_connection


def is_vip(user_id):
    conn = get_connection()
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
    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE is_vip = 1 AND (vip_expire_date IS NULL OR vip_expire_date > ?)",
        (now_str,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def add_vip_time_to_all(days: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, vip_expire_date FROM users WHERE is_vip = 1")
    vip_users = cursor.fetchall()

    now = datetime.now()
    updated_count = 0

    for user_id, expire_str in vip_users:
        if expire_str:
            current_expire = datetime.fromisoformat(expire_str)
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
