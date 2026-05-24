from .connection import get_db  
from .utils import get_tehran_today


async def get_web_search_downloads(user_id):
    """Get web search downloads count for today"""
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT web_search_dl_count, web_search_dl_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            count, date = result
            # If date doesn't match today, reset to 0
            if date != today:
                return 0
            return count if count else 0
        return 0


async def increment_web_search_downloads(user_id):
    """Increment web search downloads count and return new count"""
    today = get_tehran_today()
    conn = await get_db()

    # Get current count
    async with conn.execute(
        "SELECT web_search_dl_count, web_search_dl_date FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()

    if result:
        current_count, date = result
        # Reset if date changed
        if date != today:
            new_count = 1
        else:
            new_count = (current_count if current_count else 0) + 1
    else:
        new_count = 1

    # Update database
    await conn.execute(
        "UPDATE users SET web_search_dl_count = ?, web_search_dl_date = ? WHERE user_id = ?",
        (new_count, today, user_id),
    )
    await conn.commit()

    from .monitoring import log_upload_success

    await log_upload_success("web_search", user_id)
    return new_count
