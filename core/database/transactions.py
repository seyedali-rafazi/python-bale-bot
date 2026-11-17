# core/database/transactions.py

from .connection import get_db
from .utils import get_tehran_now_full


async def add_transaction(user_id, amount, payload, provider_charge_id):
    current_time = get_tehran_now_full()
    pool = await get_db()
    await pool.execute(
        """
        INSERT INTO transactions (user_id, amount, payload, provider_charge_id, date)
        VALUES ($1, $2, $3, $4, $5)
        """,
        str(user_id),
        int(amount),
        payload,
        provider_charge_id,
        current_time,
    )
