# core/database/base.py

import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("SQLITE_PATH", "bot_data.db")

PG_POOL_MIN = max(1, int(os.getenv("PG_POOL_MIN", "5")))
PG_POOL_MAX = max(PG_POOL_MIN, int(os.getenv("PG_POOL_MAX", "25")))
PG_COMMAND_TIMEOUT = max(5.0, float(os.getenv("PG_COMMAND_TIMEOUT", "30.0")))


def get_pg_dsn() -> str:
    """Resolve PostgreSQL DSN from DATABASE_URL or PG_* environment variables."""
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn

    user = quote_plus(os.getenv("PG_USER", "postgres"))
    password = quote_plus(os.getenv("PG_PASSWORD", "postgres"))
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    database = os.getenv("PG_DATABASE", "bale_bot")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
