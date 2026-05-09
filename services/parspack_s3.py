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


class ProgressPercentage(object):
    """
    کلاسی برای محاسبه و نمایش لاگ پیشرفت آپلود فایل
    """

    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            # چاپ درصد پیشرفت در ترمینال
            sys.stdout.write(
                f"\r⏳ Uploading {os.path.basename(self._filename)}: {percentage:.2f}% "
                f"({self._seen_so_far} / {int(self._size)} bytes)"
            )
            sys.stdout.flush()

            # وقتی 100 درصد شد به خط بعدی برود
            if self._seen_so_far >= self._size:
                sys.stdout.write("\n✅ Upload Complete!\n")


def upload_to_s3(file_path: str, object_name: str = None) -> str:
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
        config=Config(signature_version="s3v4"),
    )

    transfer_config = TransferConfig(
        multipart_threshold=8 * 1024 * 1024,
        max_concurrency=5,
        multipart_chunksize=8 * 1024 * 1024,
        use_threads=True,
    )

    try:
        # پاس دادن Callback برای نمایش درصد پیشرفت
        s3.upload_file(
            file_path,
            ARVAN_BUCKET,
            object_name,
            Config=transfer_config,
            Callback=ProgressPercentage(file_path),
        )

        presigned_url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": ARVAN_BUCKET, "Key": object_name},
            ExpiresIn=1800,
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
