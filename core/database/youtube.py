# core/database/youtube.py

import json
import sqlite3
from .base import get_connection
from .utils import get_tehran_today


def get_yt_downloads(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute("SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        count, db_date = result
        if db_date != today:
            return 0
        return count
    return 0


def increment_yt_downloads(user_id):
    conn = get_connection()
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


def decrement_yt_downloads(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    today = get_tehran_today()

    cursor.execute("SELECT yt_count, yt_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        count, db_date = result
        if db_date == today and count > 0:
            new_count = count - 1
            cursor.execute(
                "UPDATE users SET yt_count = ? WHERE user_id = ?",
                (new_count, user_id),
            )

    conn.commit()
    conn.close()


def get_cached_video(video_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_ids FROM youtube_cache WHERE video_id = ?", (video_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        return json.loads(result[0])
    return []


def save_cached_video(video_id: str, file_ids: list):
    conn = get_connection()
    cursor = conn.cursor()
    file_ids_json = json.dumps(file_ids)
    cursor.execute(
        "INSERT OR REPLACE INTO youtube_cache (video_id, file_ids) VALUES (?, ?)",
        (video_id, file_ids_json),
    )
    conn.commit()
    conn.close()


def increment_yt_video_view(video_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE youtube_cache SET view_count = view_count + 1 WHERE video_id = ?",
        (video_id,),
    )
    conn.commit()
    conn.close()


def get_top_cached_videos(limit=10):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT video_id, file_ids, view_count FROM youtube_cache ORDER BY view_count DESC LIMIT ?",
        (limit,),
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results
