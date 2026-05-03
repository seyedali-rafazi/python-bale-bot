# services/parspack_s3.py

import os
import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError

# این مقادیر را در فایل .env خود قرار دهید یا اینجا جایگزین کنید
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.parspack.com")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "YOUR_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "YOUR_SECRET_KEY")
S3_BUCKET = os.getenv("S3_BUCKET", "YOUR_BUCKET_NAME")


def upload_to_s3(file_path: str, object_name: str = None) -> str:
    """
    فایل را در سرور ابری آپلود کرده و لینک دانلود عمومی آن را برمی‌گرداند.
    """
    if object_name is None:
        object_name = os.path.basename(file_path)

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )

    try:
        # آپلود فایل
        s3.upload_file(
            file_path,
            S3_BUCKET,
            object_name,
            ExtraArgs={"ACL": "public-read"},  # برای اینکه لینک در دسترس عموم باشد
        )

        # ساخت لینک دانلود
        # اگر پارس‌پک ساختار دامنه سفارشی دارد، این بخش را مطابق آن تغییر دهید
        file_url = f"{S3_ENDPOINT}/{S3_BUCKET}/{object_name}"
        return file_url

    except FileNotFoundError:
        print("❌ The file was not found")
        return None
    except NoCredentialsError:
        print("❌ Credentials not available")
        return None
    except Exception as e:
        print(f"❌ S3 Upload Error: {e}")
        return None
