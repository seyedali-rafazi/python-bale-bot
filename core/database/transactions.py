# core/database/transactions.py

import aiosqlite
from .base import DB_NAME
from .utils import get_tehran_now_full


async def add_transaction(user_id, amount, payload, provider_charge_id):
    current_time = get_tehran_now_full()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, payload, provider_charge_id, date) VALUES (?, ?, ?, ?, ?)",
            (str(user_id), amount, payload, provider_charge_id, current_time),
        )
        await conn.commit()
