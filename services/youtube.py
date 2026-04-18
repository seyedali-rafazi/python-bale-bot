import os
import glob
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# حداکثر حجم مجاز برای ارسال ویدیو در تلگرام (50 مگابایت)
MAX_TG_VIDEO_SIZE = 50 * 1024 * 1024


def download_youtube_video(url):
    ydl_opts = {
        "proxy": PROXY,
        "format": (
            "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=480]+bestaudio/"
            "best[height<=480][ext=mp4]/"
            "best[height<=480]/"
            "worst"
        ),
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "video")
            # پیدا کردن فایل واقعی دانلود شده
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            mp4_files = [f for f in files if f.endswith(".mp4")]
            if mp4_files:
                return os.path.abspath(mp4_files[0])
            elif files:
                return os.path.abspath(files[0])
            return None
    except Exception as e:
        print(f"Error downloading YT Video: {e}")
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
        "quiet": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown Title")
            performer = info.get("uploader", "Unknown Artist")
            video_id = info.get("id", "audio")
            mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
            if os.path.exists(mp3_path):
                return os.path.abspath(mp3_path), title, performer
            # فال‌بک: جستجوی فایل
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            mp3_files = [f for f in files if f.endswith(".mp3")]
            if mp3_files:
                return os.path.abspath(mp3_files[0]), title, performer
            return None, None, None
    except Exception as e:
        print(f"Error downloading YT Audio: {e}")
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
