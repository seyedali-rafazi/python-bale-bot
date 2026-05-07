from .base import get_connection


def get_citation_count(user_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT citation_count FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] is not None else 0


def increment_citation_count(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET citation_count = citation_count + 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_book_download_count(user_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT book_download_count FROM users WHERE user_id = ?",
        (user_id,),
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] is not None else 0


def increment_book_download_count(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET book_download_count = book_download_count + 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()
