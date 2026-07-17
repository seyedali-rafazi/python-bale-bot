# core/database/kaggle.py

from .connection import get_db
from .utils import get_tehran_today

KAGGLE_LIMIT_FREE = 1
KAGGLE_LIMIT_VIP = 5


async def get_kaggle_downloads(user_id: str) -> int:
    """Returns the number of Kaggle downloads used today by user_id."""
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT kaggle_count, kaggle_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            count, db_date = result
            return count if db_date == today else 0
        return 0


async def increment_kaggle_downloads(user_id: str) -> None:
    """Increments Kaggle download counter for today."""
    today = get_tehran_today()
    conn = await get_db()
    async with conn.execute(
        "SELECT kaggle_count, kaggle_date FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        result = await cursor.fetchone()

    if result:
        count, db_date = result
        new_count = 1 if db_date != today else count + 1
        await conn.execute(
            "UPDATE users SET kaggle_count = ?, kaggle_date = ? WHERE user_id = ?",
            (new_count, today, user_id),
        )
    await conn.commit()
    from .monitoring import log_upload_success

    await log_upload_success("kaggle", user_id)
