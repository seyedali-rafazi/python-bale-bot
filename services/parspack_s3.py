# services/parspack_s3.py


import os
import sys
import threading
import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError
from boto3.s3.transfer import TransferConfig

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


class ProgressPercentage(object):
    def __init__(self, filename, progress_dict=None):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()
        self._progress_dict = progress_dict

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100

            # آپدیت دیکشنری برای تلگرام
            if self._progress_dict is not None:
                # import تابع ساخت نوار از youtube.py در بالای فایل یا کپی آن
                filled = int((percentage / 100) * 10)
                bar = "█" * filled + "░" * (10 - filled)
                self._progress_dict["text"] = (
                    f"☁️ در حال آپلود ابری...\n[{bar}] $$ {percentage:.1f} \\% $$"
                )

            sys.stdout.write(f"\r⏳ Uploading: {percentage:.2f}%")
            sys.stdout.flush()


def upload_to_s3(
    file_path: str, object_name: str = None, progress_dict: dict = None
) -> str:
    """
    فایل را در سرور ابری آپلود کرده و یک لینک دانلود موقت برمی‌گرداند.
    """
    if object_name is None:
        object_name = os.path.basename(file_path)

    s3 = boto3.client(
        "s3",
        endpoint_url=ARVAN_ENDPOINT,
        aws_access_key_id=ARVAN_ACCESS_KEY,
        aws_secret_access_key=ARVAN_SECRET_KEY,
        config=Config(signature_version="s3v4", max_pool_connections=MAX_POOL_CONNECTIONS),
    )

    transfer_config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        max_concurrency=MAX_CONCURRENCY,
        multipart_chunksize=MULTIPART_CHUNKSIZE,
        use_threads=True,
    )

    try:
        s3.upload_file(
            file_path,
            ARVAN_BUCKET,
            object_name,
            Config=transfer_config,
            Callback=ProgressPercentage(file_path, progress_dict),
        )

        presigned_url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": ARVAN_BUCKET, "Key": object_name},
            ExpiresIn=10800,
        )

        return presigned_url

    except FileNotFoundError:
        print("\n❌ The file was not found")
        return None
    except NoCredentialsError:
        print("\n❌ Credentials not available")
        return None
    except Exception as e:
        print(f"\n❌ S3 Upload Error: {e}")
        return None
