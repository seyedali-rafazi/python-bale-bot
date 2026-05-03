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


def search_tiktok_videos(query: str, max_results: int = 10):
    """جستجو در تیک تاک بر اساس هشتگ/موضوع"""
    url = f"https://www.tiktok.com/tag/{query.replace(' ', '')}"

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print",
        "%(title)s|||%(webpage_url)s",
        "--playlist-end",
        str(max_results),
        url,
    ]

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
        )
        results = []
        for line in result.stdout.splitlines():
            if "|||" in line:
                title, link = line.split("|||", 1)
                results.append({"title": title[:50] + "...", "url": link})
        return results
    except Exception as e:
        print(f"Error searching TikTok: {e}")
        return []


def get_tiktok_trends():
    return search_tiktok_videos("fyp", 10)
