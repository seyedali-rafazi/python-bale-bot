# core/database/transactions.py

from .base import get_connection
from .utils import get_tehran_now_full


def add_transaction(user_id, amount, payload, provider_charge_id):
    conn = get_connection()
    cursor = conn.cursor()
    current_time = get_tehran_now_full()
    cursor.execute(
        """
        INSERT INTO transactions (user_id, amount, payload, provider_charge_id, date)
        VALUES (?, ?, ?, ?, ?)
    """,
        (str(user_id), amount, payload, provider_charge_id, current_time),
    )
    conn.commit()
    conn.close()
