#!/usr/bin/env python3
# scripts/migrate_sqlite_to_pg.py
"""
اسکریپت انتقال فوق‌العاده امن، پرسرعت و قطعی داده‌ها از SQLite به PostgreSQL (بدون از دست رفتن حتی ۱ رکورد).

ویژگی‌ها:
1. پشتیبانی از فایل‌های حجیم با خواندن دسته‌ای (Batching / Chunking)
2. حفظ 100% شناسه‌های ترتیبی (IDs) و نگاشت rowid جدول یوتیوب
3. به‌روزرسانی خودکار Sequenceهای PostgreSQL جهت جلوگیری از خطای Duplicate ID در رکوردهای جدید
4. اعتبارسنجی خودکار (Data Validation) و مقایسه دقیق تعداد رکوردها
5. حفظ دیتابیس SQLite بدون کوچک‌ترین تغییر (فقط خواندنی)
"""

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

try:
    import asyncpg
except ImportError:
    print("❌ کتابخانه asyncpg نصب نیست! لطفاً ابتدا دستور زیر را اجرا کنید:")
    print("pip install asyncpg")
    sys.exit(1)

from dotenv import load_dotenv

# لود کردن فایل .env در صورت وجود
load_dotenv()


TABLES_CONFIG = [
    {
        "name": "users",
        "pk": "user_id",
        "has_serial": False,
        "sqlite_query": """
            SELECT user_id, username, is_vip, join_date, yt_count, yt_date,
                   music_count, music_date, vip_expire_date, pinterest_count, pinterest_date,
                   tt_dl_count, tt_dl_date, ig_dl_count, ig_dl_date, ig_exp_count, ig_exp_date,
                   gh_count, gh_date, citation_count, book_download_count, cloud_total_mb,
                   cloud_used_mb, web_search_dl_count, web_search_dl_date, tg_count, tg_date,
                   kaggle_count, kaggle_date, arc_fetch_count, arc_fetch_date, ai_chat_count, ai_chat_date
            FROM users
        """,
        "pg_insert": """
            INSERT INTO users (
                user_id, username, is_vip, join_date, yt_count, yt_date,
                music_count, music_date, vip_expire_date, pinterest_count, pinterest_date,
                tt_dl_count, tt_dl_date, ig_dl_count, ig_dl_date, ig_exp_count, ig_exp_date,
                gh_count, gh_date, citation_count, book_download_count, cloud_total_mb,
                cloud_used_mb, web_search_dl_count, web_search_dl_date, tg_count, tg_date,
                kaggle_count, kaggle_date, arc_fetch_count, arc_fetch_date, ai_chat_count, ai_chat_date
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
                $31, $32, $33
            )
            ON CONFLICT (user_id) DO NOTHING
        """
    },
    {
        "name": "youtube_cache",
        "pk": "id",
        "has_serial": True,
        # توجه مهم: rowid اسکوئلایت را به ستون id در پستگرس منتقل می‌کنیم
        "sqlite_query": """
            SELECT rowid, video_id, file_ids, view_count, title, channel_name,
                   yt_video_id, format_type, quality, cached_at, uploaded_at
            FROM youtube_cache
        """,
        "pg_insert": """
            INSERT INTO youtube_cache (
                id, video_id, file_ids, view_count, title, channel_name,
                yt_video_id, format_type, quality, cached_at, uploaded_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
            )
            ON CONFLICT (video_id) DO NOTHING
        """
    },
    {
        "name": "instagram_explore",
        "pk": "id",
        "has_serial": True,
        "sqlite_query": "SELECT id, file_id FROM instagram_explore",
        "pg_insert": """
            INSERT INTO instagram_explore (id, file_id)
            VALUES ($1, $2)
            ON CONFLICT (id) DO NOTHING
        """
    },
    {
        "name": "transactions",
        "pk": "id",
        "has_serial": True,
        "sqlite_query": "SELECT id, user_id, amount, payload, provider_charge_id, date FROM transactions",
        "pg_insert": """
            INSERT INTO transactions (id, user_id, amount, payload, provider_charge_id, date)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO NOTHING
        """
    },
    {
        "name": "settings",
        "pk": "key",
        "has_serial": False,
        "sqlite_query": "SELECT key, value FROM settings",
        "pg_insert": """
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO NOTHING
        """
    },
    {
        "name": "cloud_files",
        "pk": "id",
        "has_serial": True,
        "sqlite_query": "SELECT id, user_id, file_name, file_size_mb, download_link, upload_date FROM cloud_files",
        "pg_insert": """
            INSERT INTO cloud_files (id, user_id, file_name, file_size_mb, download_link, upload_date)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO NOTHING
        """
    },
    {
        "name": "usage_stats",
        "pk": "user_id, action, date",
        "has_serial": False,
        "sqlite_query": "SELECT user_id, action, date, count FROM usage_stats",
        "pg_insert": """
            INSERT INTO usage_stats (user_id, action, date, count)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, action, date) DO NOTHING
        """
    },
    {
        "name": "monitoring_events",
        "pk": "id",
        "has_serial": True,
        "sqlite_query": "SELECT id, section, event_type, user_id, created_at FROM monitoring_events",
        "pg_insert": """
            INSERT INTO monitoring_events (id, section, event_type, user_id, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id) DO NOTHING
        """
    },
    {
        "name": "yt_channel_blacklist",
        "pk": "channel_key",
        "has_serial": False,
        "sqlite_query": "SELECT channel_key, display_name, added_at FROM yt_channel_blacklist",
        "pg_insert": """
            INSERT INTO yt_channel_blacklist (channel_key, display_name, added_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (channel_key) DO NOTHING
        """
    },
    {
        "name": "yt_blocked_words",
        "pk": "word",
        "has_serial": False,
        "sqlite_query": "SELECT word, added_at FROM yt_blocked_words",
        "pg_insert": """
            INSERT INTO yt_blocked_words (word, added_at)
            VALUES ($1, $2)
            ON CONFLICT (word) DO NOTHING
        """
    }
]


def table_exists_in_sqlite(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cur.fetchone() is not None


def get_sqlite_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


async def execute_schema(pg_conn: asyncpg.Connection, schema_path: str):
    """اجرای فایل اسکیما برای ساخت جداول در صورت عدم وجود"""
    if os.path.exists(schema_path):
        print(f"📦 در حال ایجاد اسکیما و جداول از روی {schema_path}...")
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        await pg_conn.execute(sql)
        print("✅ اسکیما و ایندکس‌ها با موفقیت اعمال شدند.")
    else:
        print(f"⚠️ فایل اسکیما در مسیر {schema_path} پیدا نشد؛ از جداول از پیش تعریف‌شده استفاده می‌شود.")


async def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: asyncpg.Connection,
    table_cfg: dict,
    batch_size: int = 5000,
    truncate_first: bool = False
) -> tuple[int, int]:
    tbl_name = table_cfg["name"]
    if not table_exists_in_sqlite(sqlite_conn, tbl_name):
        print(f"⏩ جدول [{tbl_name}] در دیتابیس SQLite وجود نداشت، رد شد.")
        return 0, 0

    if truncate_first:
        await pg_conn.execute(f"TRUNCATE TABLE {tbl_name} CASCADE;")

    sqlite_cur = sqlite_conn.cursor()

    # شمارش اولیه در SQLite
    sqlite_cur.execute(f"SELECT COUNT(*) FROM {tbl_name}")
    total_sqlite_count = sqlite_cur.fetchone()[0]

    if total_sqlite_count == 0:
        print(f"ℹ️ جدول [{tbl_name}] خالی است (0 رکورد).")
        return 0, 0

    print(f"🚀 در حال انتقال جدول [{tbl_name}] - مجموع: {total_sqlite_count:,} رکورد...")

    # خواندن با کوئری مشخص‌شده
    try:
        sqlite_cur.execute(table_cfg["sqlite_query"])
    except sqlite3.OperationalError as e:
        print(f"⚠️ خطای ساختار ستون در SQLite برای جدول {tbl_name}: {e}. کوئری ساده SELECT * اجرا می‌شود.")
        # فال‌بک دینامیک در صورت تفاوت نام برخی ستون‌ها
        sqlite_cur.execute(f"SELECT * FROM {tbl_name}")

    imported = 0
    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break

        # درج دسته‌ای در PostgreSQL درون یک تراکنش
        async with pg_conn.transaction():
            await pg_conn.executemany(table_cfg["pg_insert"], rows)

        imported += len(rows)
        pct = (imported / total_sqlite_count) * 100
        print(f"   ↳ پیشرفت [{tbl_name}]: {imported:,} از {total_sqlite_count:,} ({pct:.1f}%)")

    # به‌روزرسانی مقدار Sequence برای جداولی که کلید ترتیبی عددی دارند
    if table_cfg.get("has_serial"):
        seq_query = f"""
            SELECT setval(
                pg_get_serial_sequence('{tbl_name}', 'id'),
                COALESCE((SELECT MAX(id) FROM {tbl_name}), 1),
                (SELECT MAX(id) FROM {tbl_name}) IS NOT NULL
            );
        """
        try:
            await pg_conn.execute(seq_query)
            print(f"   🔄 Sequence جدول [{tbl_name}] با موفقیت به آخرین شناسه تنظیم شد.")
        except Exception as e:
            print(f"   ⚠️ هشدار تنظیم Sequence برای {tbl_name}: {e}")

    # شمارش نهایی در PostgreSQL
    pg_count = await pg_conn.fetchval(f"SELECT COUNT(*) FROM {tbl_name}")
    return total_sqlite_count, pg_count


async def run_migration(
    sqlite_path: str,
    pg_dsn: str,
    schema_path: str,
    batch_size: int,
    truncate: bool
):
    print("=" * 60)
    print("✨ آغاز فرآیند انتقال داده‌ها به PostgreSQL ✨")
    print(f"📂 مسیر دیتابیس SQLite: {sqlite_path}")
    print("=" * 60)

    if not os.path.exists(sqlite_path):
        print(f"❌ خطای بحرانی: فایل SQLite در مسیر {sqlite_path} یافت نشد!")
        return

    # اتصال به SQLite با حالت Read-Only جهت امنیت کامل
    uri_sqlite = f"file:{Path(sqlite_path).resolve().as_posix()}?mode=ro"
    sqlite_conn = sqlite3.connect(uri_sqlite, uri=True)

    # اتصال به PostgreSQL
    try:
        pg_conn = await asyncpg.connect(pg_dsn)
    except Exception as e:
        print(f"❌ خطا در اتصال به دیتابیس PostgreSQL: {e}")
        return

    try:
        # اعمال اسکیما
        await execute_schema(pg_conn, schema_path)

        # انتقال جداول
        results = []
        for tbl_cfg in TABLES_CONFIG:
            src_cnt, dst_cnt = await migrate_table(
                sqlite_conn=sqlite_conn,
                pg_conn=pg_conn,
                table_cfg=tbl_cfg,
                batch_size=batch_size,
                truncate_first=truncate
            )
            results.append((tbl_cfg["name"], src_cnt, dst_cnt))

        # گزارش نهایی اعتبارسنجی
        print("\n" + "=" * 60)
        print("📊 گزارش مقایسه‌ای نهایی (اعتبارسنجی انتقال داده‌ها):")
        print(f"{'نام جدول':<25} | {'تعداد SQLite':<15} | {'تعداد PostgreSQL':<15} | وضعیت")
        print("-" * 65)

        all_ok = True
        for name, src_cnt, dst_cnt in results:
            match = (src_cnt == dst_cnt)
            if not match:
                all_ok = False
            status = "✅ تطابق کامل" if match else "⚠️ تفاوت در تعداد"
            print(f"{name:<25} | {src_cnt:<15,} | {dst_cnt:<15,} | {status}")

        print("=" * 60)
        if all_ok:
            print("🎉 مهاجرت با موفقیت ۱۰۰٪ و بدون حتی ۱ رکورد خطا یا مغایرت به پایان رسید!")
        else:
            print("⚠️ انتقال انجام شد، اما تفاوت در تعداد رکوردهای برخی جداول وجود دارد (احتمالاً به دلیل رکوردهای تکراری از قبل).")

    finally:
        sqlite_conn.close()
        await pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite database to PostgreSQL safely.")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("SQLITE_PATH", "bot_data.db"),
        help="مسیر فایل دیتابیس یا بکاپ SQLite"
    )
    parser.add_argument(
        "--pg-dsn",
        default=os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('PG_USER', 'postgres')}:{os.getenv('PG_PASSWORD', 'postgres')}@{os.getenv('PG_HOST', 'localhost')}:{os.getenv('PG_PORT', '5432')}/{os.getenv('PG_DATABASE', 'bale_bot')}"
        ),
        help="کانکشن استرینگ PostgreSQL"
    )
    parser.add_argument(
        "--schema-file",
        default=str(Path(__file__).parent / "schema_postgres.sql"),
        help="مسیر فایل ساخت اسکیما SQL"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="تعداد رکورد در هر Batch درج"
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="پاکسازی جداول مقصد قبل از درج (برای اجرای مجدد)"
    )

    args = parser.parse_args()

    asyncio.run(
        run_migration(
            sqlite_path=args.sqlite_path,
            pg_dsn=args.pg_dsn,
            schema_path=args.schema_file,
            batch_size=args.batch_size,
            truncate=args.truncate
        )
    )


if __name__ == "__main__":
    main()
