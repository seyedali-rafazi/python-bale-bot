# core/database/cloud.py

from .connection import get_db
from .utils import get_tehran_now_full


async def get_user_cloud_info(user_id):
    """Get user's cloud storage information"""
    conn = await get_db()
    async with conn.execute(
        "SELECT cloud_total_mb, cloud_used_mb FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            return {"total_mb": result[0], "used_mb": result[1]}
        return None


async def get_available_cloud_mb(user_id):
    """Get available cloud storage space for user"""
    conn = await get_db()
    async with conn.execute(
        "SELECT cloud_total_mb, cloud_used_mb FROM users WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            total_mb, used_mb = result
            return total_mb - used_mb
        return None


async def add_cloud_storage(user_id, size_mb: int):
    """Add cloud storage space for user"""
    conn = await get_db()
    await conn.execute(
        "UPDATE users SET cloud_total_mb = cloud_total_mb + ? WHERE user_id = ?",
        (size_mb, user_id),
    )
    await conn.commit()


async def reduce_cloud_storage(user_id, size_mb: int):
    """Reduce available cloud storage when file is uploaded"""
    conn = await get_db()
    await conn.execute(
        "UPDATE users SET cloud_used_mb = cloud_used_mb + ? WHERE user_id = ?",
        (size_mb, user_id),
    )
    await conn.commit()


async def add_cloud_file(user_id, file_name: str, file_size_mb: int, download_link: str):
    """Add uploaded file to cloud files database"""
    conn = await get_db()
    upload_date = get_tehran_now_full()
    await conn.execute(
        """
        INSERT INTO cloud_files (user_id, file_name, file_size_mb, download_link, upload_date)
        VALUES (?, ?, ?, ?, ?)
    """,
        (user_id, file_name, file_size_mb, download_link, upload_date),
    )
    await conn.commit()


async def get_user_cloud_files(user_id):
    """Get all files uploaded by user to cloud"""
    conn = await get_db()
    async with conn.execute(
        """
        SELECT id, file_name, file_size_mb, download_link, upload_date 
        FROM cloud_files 
        WHERE user_id = ? 
        ORDER BY upload_date DESC
    """,
        (user_id,),
    ) as cursor:
        return await cursor.fetchall()


async def delete_cloud_file(user_id, file_id: int):
    """Delete a file from cloud and free up storage space"""
    conn = await get_db()
    
    # Get file size to free up space
    async with conn.execute(
        "SELECT file_size_mb FROM cloud_files WHERE id = ? AND user_id = ?",
        (file_id, user_id),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            file_size_mb = result[0]
            
            # Delete the file from database
            await conn.execute(
                "DELETE FROM cloud_files WHERE id = ? AND user_id = ?",
                (file_id, user_id),
            )
            
            # Reduce the used space
            await conn.execute(
                "UPDATE users SET cloud_used_mb = MAX(0, cloud_used_mb - ?) WHERE user_id = ?",
                (file_size_mb, user_id),
            )
            
            await conn.commit()
            return True
    
    return False


async def get_cloud_usage_stats(user_id):
    """Get detailed cloud storage usage statistics"""
    conn = await get_db()
    async with conn.execute(
        """
        SELECT 
            (SELECT COUNT(*) FROM cloud_files WHERE user_id = ?) as file_count,
            (SELECT COALESCE(SUM(file_size_mb), 0) FROM cloud_files WHERE user_id = ?) as total_file_size,
            (SELECT cloud_total_mb FROM users WHERE user_id = ?) as total_quota,
            (SELECT cloud_used_mb FROM users WHERE user_id = ?) as used_quota
    """,
        (user_id, user_id, user_id, user_id),
    ) as cursor:
        result = await cursor.fetchone()
        if result:
            file_count, total_file_size, total_quota, used_quota = result
            return {
                "file_count": file_count or 0,
                "total_file_size": total_file_size or 0,
                "total_quota": total_quota or 5000,
                "used_quota": used_quota or 0,
            }
        return None
