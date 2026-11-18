# core/database/cloud.py

from datetime import datetime
from .connection import get_db
from .utils import get_tehran_now_full


async def get_user_cloud_info(user_id):
    """Get user's cloud storage information."""
    uid = str(user_id)
    pool = await get_db()
    result = await pool.fetchrow(
        "SELECT cloud_total_mb, cloud_used_mb FROM users WHERE user_id = $1",
        uid,
    )
    if result:
        return {
            "total_mb": result["cloud_total_mb"] or 0,
            "used_mb": result["cloud_used_mb"] or 0,
        }
    return None


async def get_available_cloud_mb(user_id):
    """Get available cloud storage space for user."""
    info = await get_user_cloud_info(user_id)
    if info is not None:
        return info["total_mb"] - info["used_mb"]
    return None


async def add_cloud_storage(user_id, size_mb: float):
    """Add cloud storage space for user and return updated totals if user exists."""
    uid = str(user_id)
    pool = await get_db()
    row = await pool.fetchrow(
        """
        UPDATE users
        SET cloud_total_mb = COALESCE(cloud_total_mb, 0) + $1
        WHERE user_id = $2
        RETURNING cloud_total_mb, cloud_used_mb
        """,
        float(size_mb),
        uid,
    )
    if row is None:
        return None
    return {
        "total_mb": row["cloud_total_mb"] or 0,
        "used_mb": row["cloud_used_mb"] or 0,
    }


async def reduce_cloud_storage(user_id, size_mb: float):
    """Reduce available cloud storage when file is uploaded."""
    uid = str(user_id)
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET cloud_used_mb = COALESCE(cloud_used_mb, 0) + $1 WHERE user_id = $2",
        float(size_mb),
        uid,
    )


async def add_cloud_file(
    user_id, file_name: str, file_size_mb: float, download_link: str
):
    """Add uploaded file to cloud files database."""
    uid = str(user_id)
    pool = await get_db()
    upload_date = get_tehran_now_full()
    await pool.execute(
        """
        INSERT INTO cloud_files (user_id, file_name, file_size_mb, download_link, upload_date)
        VALUES ($1, $2, $3, $4, $5)
        """,
        uid,
        file_name,
        float(file_size_mb),
        download_link,
        upload_date,
    )


async def record_cloud_uploads(
    user_id,
    files: list[tuple[str, float, str]],
) -> float:
    """
    Atomically insert one or more cloud_files rows and increment cloud_used_mb
    inside a single PostgreSQL transaction.
    Returns total size added in MB.
    """
    if not files:
        return 0.0
    uid = str(user_id)
    upload_date = get_tehran_now_full()
    total_mb = sum(float(size_mb) for _, size_mb, _ in files)
    records = [
        (uid, file_name, float(size_mb), download_link, upload_date)
        for file_name, size_mb, download_link in files
    ]
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO cloud_files (user_id, file_name, file_size_mb, download_link, upload_date)
                VALUES ($1, $2, $3, $4, $5)
                """,
                records,
            )
            await conn.execute(
                "UPDATE users SET cloud_used_mb = COALESCE(cloud_used_mb, 0) + $1 WHERE user_id = $2",
                total_mb,
                uid,
            )
    return total_mb


async def record_cloud_upload(
    user_id,
    file_name: str,
    file_size_mb: float,
    download_link: str,
) -> float:
    """Atomically record a single cloud upload and deduct storage quota."""
    return await record_cloud_uploads(
        user_id, [(file_name, float(file_size_mb), download_link)]
    )


async def get_user_cloud_files(user_id, limit: int | None = None):
    """Get files uploaded by user to cloud (newest first)."""
    uid = str(user_id)
    pool = await get_db()
    if limit is not None:
        return await pool.fetch(
            """
            SELECT id, file_name, file_size_mb, download_link, upload_date
            FROM cloud_files
            WHERE user_id = $1
            ORDER BY upload_date DESC
            LIMIT $2
            """,
            uid,
            int(limit),
        )
    return await pool.fetch(
        """
        SELECT id, file_name, file_size_mb, download_link, upload_date
        FROM cloud_files
        WHERE user_id = $1
        ORDER BY upload_date DESC
        """,
        uid,
    )


async def delete_cloud_file(user_id, file_id: int) -> bool:
    """Delete a file from cloud and free up storage space atomically."""
    uid = str(user_id)
    pool = await get_db()

    async with pool.acquire() as conn:
        async with conn.transaction():
            deleted_size = await conn.fetchval(
                "DELETE FROM cloud_files WHERE id = $1 AND user_id = $2 RETURNING file_size_mb",
                int(file_id),
                uid,
            )
            if deleted_size is None:
                return False

            await conn.execute(
                """
                UPDATE users
                SET cloud_used_mb = GREATEST(0, COALESCE(cloud_used_mb, 0) - $1)
                WHERE user_id = $2
                """,
                float(deleted_size),
                uid,
            )
            return True


async def get_cloud_usage_stats(user_id):
    """Get detailed cloud storage usage statistics in a single LEFT JOIN query."""
    uid = str(user_id)
    pool = await get_db()
    result = await pool.fetchrow(
        """
        SELECT
            COALESCE(cf.file_count, 0) AS file_count,
            COALESCE(cf.total_file_size, 0) AS total_file_size,
            u.cloud_total_mb AS total_quota,
            u.cloud_used_mb AS used_quota
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS file_count, COALESCE(SUM(file_size_mb), 0) AS total_file_size
            FROM cloud_files
            WHERE user_id = $1
            GROUP BY user_id
        ) cf ON cf.user_id = u.user_id
        WHERE u.user_id = $1
        """,
        uid,
    )
    if result:
        return {
            "file_count": result["file_count"] or 0,
            "total_file_size": result["total_file_size"] or 0,
            "total_quota": result["total_quota"] or 0,
            "used_quota": result["used_quota"] or 0,
        }
    return None


async def give_5gb_to_existing_vips():
    """دادن 5000 مگابایت به کاربرانی که در حال حاضر VIP فعال هستند اما حجم ابری ندارند"""
    now_str = datetime.now().isoformat()
    pool = await get_db()
    await pool.execute(
        """
        UPDATE users
        SET cloud_total_mb = COALESCE(cloud_total_mb, 0) + 5000
        WHERE is_vip = 1
          AND (vip_expire_date IS NULL OR vip_expire_date > $1)
          AND (cloud_total_mb IS NULL OR cloud_total_mb = 0)
        """,
        now_str,
    )
