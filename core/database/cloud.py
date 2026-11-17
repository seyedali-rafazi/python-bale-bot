# core/database/cloud.py

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
    uid = str(user_id)
    pool = await get_db()
    result = await pool.fetchrow(
        "SELECT cloud_total_mb, cloud_used_mb FROM users WHERE user_id = $1",
        uid,
    )
    if result:
        total_mb = result["cloud_total_mb"] or 0
        used_mb = result["cloud_used_mb"] or 0
        return total_mb - used_mb
    return None


async def add_cloud_storage(user_id, size_mb: float):
    """Add cloud storage space for user."""
    uid = str(user_id)
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET cloud_total_mb = COALESCE(cloud_total_mb, 0) + $1 WHERE user_id = $2",
        float(size_mb),
        uid,
    )


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


async def get_user_cloud_files(user_id):
    """Get all files uploaded by user to cloud."""
    uid = str(user_id)
    pool = await get_db()
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
    """Get detailed cloud storage usage statistics."""
    uid = str(user_id)
    pool = await get_db()
    result = await pool.fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM cloud_files WHERE user_id = $1) AS file_count,
            (SELECT COALESCE(SUM(file_size_mb), 0) FROM cloud_files WHERE user_id = $1) AS total_file_size,
            (SELECT cloud_total_mb FROM users WHERE user_id = $1) AS total_quota,
            (SELECT cloud_used_mb FROM users WHERE user_id = $1) AS used_quota
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
    """دادن 5000 مگابایت به کاربرانی که در حال حاضر VIP هستند اما حجم ابری ندارند"""
    pool = await get_db()
    await pool.execute(
        """
        UPDATE users
        SET cloud_total_mb = COALESCE(cloud_total_mb, 0) + 5000
        WHERE is_vip = 1 AND (cloud_total_mb IS NULL OR cloud_total_mb = 0)
        """
    )
