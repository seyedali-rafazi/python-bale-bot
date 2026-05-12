# core/database/transactions.py

import aiosqlite  # این خط را نگه می‌داریم چون `aiosqlite.Row` نیاز به آن دارد
from .connection import get_db  # تغییر: به جای DB_NAME، از get_db استفاده می‌کنیم
from .utils import get_tehran_now_full


async def add_transaction(user_id, amount, payload, provider_charge_id):
    current_time = get_tehran_now_full()
    conn = await get_db()  # تغییر: استفاده از اتصال واحد
    await conn.execute(
        "INSERT INTO transactions (user_id, amount, payload, provider_charge_id, date) VALUES (?, ?, ?, ?, ?)",
        (str(user_id), amount, payload, provider_charge_id, current_time),
    )
    await conn.commit()
