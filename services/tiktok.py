# services/tiktok.py
import os
import uuid
import subprocess
from dotenv import load_dotenv

load_dotenv()
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_tiktok_video(url: str):
    """دانلود ویدیوی تیک‌تاک"""
    req_id = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--force-ipv6",  # در صورت مشکل در سرور، این خط را حذف کنید
        "-f",
        "bestvideo+bestaudio/best",
        "-o",
        output_template,
        "--no-playlist",
        url,
    ]

    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if process.returncode != 0:
        print(f"❌ TikTok DL Error: {process.stderr}")
        return None

    # پیدا کردن فایل دانلودی
    import glob

    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
    return files[0] if files else None


def search_tiktok_videos(query: str, max_results: int = 10):
    """جستجو در تیک تاک بر اساس هشتگ/موضوع"""
    # از آنجایی که تیک‌تاک سرچ رسمی ندارد، هشتگ‌ها بهترین گزینه برای yt-dlp هستند.
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
    """گرفتن ویدیوهای ترند (شبیه‌سازی شده از طریق صفحه اصلی/explore)"""
    # اگر yt-dlp روی ترندها بسته بود، می‌توانید اینجا API جایگزین بگذارید
    # فعلا از هشتگ ترند fyp استفاده میکنیم که همیشه ویدیوهای ترند دارد.
    return search_tiktok_videos("fyp", 10)
