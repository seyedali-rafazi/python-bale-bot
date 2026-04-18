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
    """دانلود ویدیو با کیفیت 480p و لاگ کامل"""

    def progress_hook(d):
        if d["status"] == "finished":
            print(f"✅ Download finished: {d.get('filename', 'unknown')}")

    ydl_opts = {
        "proxy": PROXY,
        "format": "best[height<=480][ext=mp4]/best[height<=480]/worst[ext=mp4]/worst",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": False,  # فعلاً False تا ببینیم چی میشه
        "no_warnings": False,
        "progress_hooks": [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🔍 Extracting info from: {url}")
            info = ydl.extract_info(url, download=True)

            video_id = info.get("id", "unknown")
            print(f"📹 Video ID: {video_id}")
            print(f"📁 Looking in: {DOWNLOAD_DIR}")

            # جستجوی فایل
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            print(f"🔎 Found files: {files}")

            if files:
                final_file = files[0]
                file_size = os.path.getsize(final_file)
                print(
                    f"✅ Final file: {final_file} ({file_size / (1024 * 1024):.2f} MB)"
                )
                return os.path.abspath(final_file)

            # اگه با ID پیدا نشد، همه فایل‌های دایرکتوری رو چک کن
            all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
            print(f"📂 All files in download dir: {all_files}")

            if all_files:
                # جدیدترین فایل رو برگردون
                latest = max(all_files, key=os.path.getctime)
                print(f"⚠️ Using latest file: {latest}")
                return os.path.abspath(latest)

            print("❌ No file found!")
            return None

    except Exception as e:
        print(f"❌ Error downloading YT Video: {e}")
        import traceback

        traceback.print_exc()
        return None


def download_youtube_audio(url):
    """دانلود صدا با لاگ کامل"""

    def progress_hook(d):
        if d["status"] == "finished":
            print(f"✅ Audio download finished: {d.get('filename', 'unknown')}")

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
        "progress_hooks": [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🔍 Extracting audio from: {url}")
            info = ydl.extract_info(url, download=True)

            title = info.get("title", "Unknown Title")
            performer = info.get("uploader", "Unknown Artist")
            video_id = info.get("id", "unknown")

            print(f"🎵 Audio ID: {video_id}")

            # جستجوی فایل MP3
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            mp3_files = [f for f in files if f.endswith(".mp3")]

            print(f"🔎 Found files: {files}")
            print(f"🎵 MP3 files: {mp3_files}")

            if mp3_files:
                return os.path.abspath(mp3_files[0]), title, performer

            # فال‌بک
            all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.mp3"))
            if all_files:
                latest = max(all_files, key=os.path.getctime)
                print(f"⚠️ Using latest MP3: {latest}")
                return os.path.abspath(latest), title, performer

            print("❌ No MP3 file found!")
            return None, None, None

    except Exception as e:
        print(f"❌ Error downloading YT Audio: {e}")
        import traceback

        traceback.print_exc()
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
