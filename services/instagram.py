# services/instagram.py

import os
import uuid
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
DOWNLOAD_DIR = "ig_downloads"
COOKIES_FILE = "insta_cookies.txt"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


def download_instagram(url):
    req_id = uuid.uuid4().hex

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/{req_id}_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "sleep_interval": 5,
        "max_sleep_interval": 15,
    }
    if os.path.isfile(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
    proxy = os.getenv("IG_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    except Exception as e:
        print(f"Error downloading with yt-dlp: {e}")
        return None
