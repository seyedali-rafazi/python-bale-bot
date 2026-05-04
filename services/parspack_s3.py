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
    فایل را در سرور ابری آپلود کرده و یک لینک دانلود موقت (Presigned URL) برمی‌گرداند.
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
        # ۱. آپلود فایل به صورت خصوصی (حذف ACL: public-read)
        s3.upload_file(file_path, ARVAN_BUCKET, object_name)

        # ۲. ساخت لینک موقت و امضاشده
        # مدت زمان اعتبار لینک به ثانیه: اینجا روی ۱ ساعت (۳۶۰۰ ثانیه) تنظیم شده است
        # می‌توانید آن را به مثلاً ۹۰۰ (۱۵ دقیقه) کاهش دهید
        presigned_url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": ARVAN_BUCKET, "Key": object_name},
            ExpiresIn=1800,
        )

        return presigned_url

    except FileNotFoundError:
        print("❌ The file was not found")
        return None
    except NoCredentialsError:
        print("❌ Credentials not available")
        return None
    except Exception as e:
        print(f"❌ S3 Upload Error: {e}")
        return None
