# services/tiktok.py
import os
import uuid
import subprocess
import glob
from dotenv import load_dotenv

load_dotenv()
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_tiktok_video(url: str):
    """دانلود ویدیوی تیک‌تاک"""
    print(f"🎬 [TikTok Service] Start downloading: {url}")
    req_id = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        "bv*+ba/b",
        "-o",
        output_template,
        "--no-playlist",
        url,
    ]

    print(f"⚙️ [TikTok Service] Running command: {' '.join(cmd)}")

    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # چاپ لاگ‌های خروجی
    print(f"📝 [TikTok Service] STDOUT:\n{process.stdout}")
    if process.stderr:
        print(f"⚠️ [TikTok Service] STDERR:\n{process.stderr}")

    if process.returncode != 0:
        print(
            f"❌ [TikTok Service] Process Failed with return code {process.returncode}"
        )
        return None

    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
    if files:
        print(f"✅ [TikTok Service] Download successful: {files[0]}")
        return files[0]
    else:
        print(
            f"❌ [TikTok Service] Command succeeded but no file found matching: tt_{req_id}.*"
        )
        return None
