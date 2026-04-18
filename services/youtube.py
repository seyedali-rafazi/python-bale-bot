# services/youtube.py

import os
import glob
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_TG_VIDEO_SIZE = 50 * 1024 * 1024


def download_youtube_video(url):
    """دانلود ویدیو - فقط اگه زیر 50MB باشه"""

    ydl_opts = {
        "proxy": PROXY,
        "format": "best[height<=480][filesize<50M]/best[height<=360][filesize<50M]/best[height<=240]/worst",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # فقط اطلاعات بگیر، دانلود نکن
            info = ydl.extract_info(url, download=False)
            filesize = info.get("filesize") or info.get("filesize_approx") or 0
            size_mb = filesize / (1024 * 1024)

            if filesize > MAX_TG_VIDEO_SIZE:
                print(f"❌ Too large: {size_mb:.1f} MB")
                return "TOO_LARGE"

            # سایز اوکیه، دانلود کن
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)

            if not files:
                all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
                if all_files:
                    files = [max(all_files, key=os.path.getctime)]

            if not files:
                return None

            final_file = files[0]
            actual_size = os.path.getsize(final_file)

            # چک نهایی بعد دانلود
            if actual_size > MAX_TG_VIDEO_SIZE:
                os.remove(final_file)
                return "TOO_LARGE"

            return os.path.abspath(final_file)

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def download_youtube_audio(url):
    ydl_opts = {
        "proxy": PROXY,
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": False,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🔍 Extracting audio from: {url}")
            info = ydl.extract_info(url, download=True)

            title = info.get("title", "Unknown Title")
            performer = info.get("uploader", "Unknown Artist")
            video_id = info.get("id", "unknown")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            mp3_files = [f for f in files if f.endswith(".mp3")]

            print(f"🔎 Found: {files} | MP3: {mp3_files}")

            if mp3_files:
                return os.path.abspath(mp3_files[0]), title, performer

            all_mp3 = glob.glob(os.path.join(DOWNLOAD_DIR, "*.mp3"))
            if all_mp3:
                latest = max(all_mp3, key=os.path.getctime)
                return os.path.abspath(latest), title, performer

            return None, None, None

    except Exception as e:
        print(f"❌ Error downloading audio: {e}")
        return None, None, None


def search_yt_videos(query, max_results=5):
    ydl_opts = {
        "proxy": PROXY,
        "extract_flat": True,
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_query = (
                f"ytsearch{max_results}:{query}"
                if not query.startswith("http")
                else query
            )
            info = ydl.extract_info(search_query, download=False)

            if "entries" in info:
                entries = info["entries"][:max_results]
            else:
                entries = [info]

            results = []
            for entry in entries:
                if entry.get("id"):
                    results.append(
                        {
                            "title": entry.get("title", "Unknown"),
                            "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                        }
                    )
            return results
    except Exception as e:
        print(f"Error searching YT: {e}")
        return []
