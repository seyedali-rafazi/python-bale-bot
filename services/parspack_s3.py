# services/parspack_s3.py


import asyncio
import logging
import os
import threading
import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError
from boto3.s3.transfer import TransferConfig

logger = logging.getLogger(__name__)

ARVAN_ENDPOINT = os.getenv("ARVAN_ENDPOINT", "https://s3.ir-thr-at1.arvanstorage.ir")
ARVAN_ACCESS_KEY = os.getenv("ARVAN_ACCESS_KEY", "YOUR_ACCESS_KEY")
ARVAN_SECRET_KEY = os.getenv("ARVAN_SECRET_KEY", "YOUR_SECRET_KEY")
ARVAN_BUCKET = os.getenv("ARVAN_BUCKET", "YOUR_BUCKET")

# ==========================================
# تنظیمات برای 10000 کاربر
# ==========================================
# تعداد بیشتری از اتصالات برای تحمل بار بالا
MAX_POOL_CONNECTIONS = 100
MAX_CONCURRENCY = 20
MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5 MB
MULTIPART_CHUNKSIZE = 5 * 1024 * 1024  # 5 MB

_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=MULTIPART_THRESHOLD,
    max_concurrency=MAX_CONCURRENCY,
    multipart_chunksize=MULTIPART_CHUNKSIZE,
    use_threads=True,
)
_S3_UPLOAD_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("S3_MAX_CONCURRENT_UPLOADS", "4"))))

_s3_client = None
_s3_client_lock = threading.Lock()


def _get_s3_client():
    """Return a shared, thread-safe boto3 S3 client reusing the connection pool."""
    global _s3_client
    if _s3_client is None:
        with _s3_client_lock:
            if _s3_client is None:
                _s3_client = boto3.client(
                    "s3",
                    endpoint_url=ARVAN_ENDPOINT,
                    aws_access_key_id=ARVAN_ACCESS_KEY,
                    aws_secret_access_key=ARVAN_SECRET_KEY,
                    config=Config(
                        signature_version="s3v4",
                        max_pool_connections=MAX_POOL_CONNECTIONS,
                        connect_timeout=15,
                        read_timeout=120,
                    ),
                )
    return _s3_client


class ProgressPercentage(object):
    def __init__(self, filename, progress_dict=None):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._last_reported_pct = -1
        self._lock = threading.Lock()
        self._progress_dict = progress_dict

    def __call__(self, bytes_amount):
        if self._size <= 0:
            return
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = min(100.0, (self._seen_so_far / self._size) * 100)
            whole_pct = int(percentage)
            if whole_pct == self._last_reported_pct and percentage < 100.0:
                return
            self._last_reported_pct = whole_pct

            # آپدیت دیکشنری برای تلگرام
            if self._progress_dict is not None:
                filled = int((percentage / 100) * 10)
                bar = "█" * filled + "░" * (10 - filled)
                self._progress_dict["text"] = (
                    f"☁️ در حال آپلود ابری...\n[{bar}] $$ {percentage:.1f} \\% $$"
                )


def generate_presigned_url_for_key(
    object_name: str, expires_in: int = 10800
) -> str | None:
    """Generate a fresh presigned download URL for an existing S3 object key."""
    if not object_name:
        return None
    try:
        s3 = _get_s3_client()
        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": ARVAN_BUCKET, "Key": object_name},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        logger.warning("S3 presign error for %s: %s", object_name, e)
        return None


def upload_to_s3_with_key(
    file_path: str, object_name: str = None, progress_dict: dict = None
) -> tuple[str | None, str | None]:
    """
    فایل را در سرور ابری آپلود کرده و (presigned_url, object_name) برمی‌گرداند.
    """
    if object_name is None:
        object_name = os.path.basename(file_path)

    s3 = _get_s3_client()

    try:
        s3.upload_file(
            file_path,
            ARVAN_BUCKET,
            object_name,
            Config=_TRANSFER_CONFIG,
            Callback=ProgressPercentage(file_path, progress_dict),
        )

        presigned_url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": ARVAN_BUCKET, "Key": object_name},
            ExpiresIn=10800,
        )

        return presigned_url, object_name

    except FileNotFoundError:
        logger.warning("S3 upload file not found: %s", file_path)
        return None, None
    except NoCredentialsError:
        logger.error("S3 credentials not available")
        return None, None
    except Exception as e:
        logger.warning("S3 Upload Error: %s", e)
        return None, None


def upload_to_s3(
    file_path: str, object_name: str = None, progress_dict: dict = None
) -> str:
    """
    فایل را در سرور ابری آپلود کرده و یک لینک دانلود موقت برمی‌گرداند.
    """
    presigned_url, _ = upload_to_s3_with_key(
        file_path, object_name=object_name, progress_dict=progress_dict
    )
    return presigned_url


async def async_generate_presigned_url_for_key(
    object_name: str, expires_in: int = 10800
) -> str | None:
    """Offload presigned URL generation (and lazy boto3 client construction) off the event loop."""
    if not object_name:
        return None
    return await asyncio.to_thread(generate_presigned_url_for_key, object_name, expires_in)


async def async_upload_to_s3_with_key(
    file_path: str,
    object_name: str = None,
    progress_dict: dict = None,
    *,
    upload_fn=None,
) -> tuple[str | None, str | None]:
    """Bounded async wrapper for S3 uploads to cap s3transfer thread contention."""
    target_fn = upload_fn or upload_to_s3_with_key
    async with _S3_UPLOAD_SEMAPHORE:
        return await asyncio.wait_for(
            asyncio.to_thread(
                target_fn, file_path, object_name, progress_dict
            ),
            timeout=300.0,
        )
