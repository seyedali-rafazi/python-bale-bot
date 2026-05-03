# services/parspack_s3.py


import os
import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError

ARVAN_ENDPOINT = os.getenv("ARVAN_ENDPOINT", "https://s3.ir-thr-at1.arvanstorage.ir")
ARVAN_ACCESS_KEY = os.getenv("ARVAN_ACCESS_KEY", "YOUR_ACCESS_KEY")
ARVAN_SECRET_KEY = os.getenv("ARVAN_SECRET_KEY", "YOUR_SECRET_KEY")
ARVAN_BUCKET = os.getenv("ARVAN_BUCKET", "YOUR_BUCKET")


def upload_to_s3(file_path: str, object_name: str = None) -> str:
    """
    فایل را در سرور ابری آروان آپلود کرده و لینک دانلود عمومی آن را برمی‌گرداند.
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

    try:
        # آپلود فایل
        s3.upload_file(
            file_path,
            ARVAN_BUCKET,
            object_name,
            ExtraArgs={"ACL": "public-read"},  # برای دسترسی عمومی به لینک
        )

        # ساخت لینک دانلود برای ابر آروان (Path-Style)
        file_url = f"{ARVAN_ENDPOINT}/{ARVAN_BUCKET}/{object_name}"
        return file_url

    except FileNotFoundError:
        print("❌ The file was not found")
        return None
    except NoCredentialsError:
        print("❌ Credentials not available")
        return None
    except Exception as e:
        print(f"❌ ArvanCloud S3 Upload Error: {e}")
        return None
