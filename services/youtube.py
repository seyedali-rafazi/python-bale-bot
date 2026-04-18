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
    """دانلود ویدیو با کیفیت 480p و فشرده‌سازی اجباری"""

    def progress_hook(d):
        if d["status"] == "finished":
            print(f"✅ Download finished: {d.get('filename', 'unknown')}")

    ydl_opts = {
        "proxy": PROXY,
        # فرمت دقیق برای 480p
        "format": "bestvideo[height<=480]+bestaudio[abr<=128]/best[height<=480]/worst",
        "format_sort": ["res:480", "br"],  # اولویت به 480p
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
        "progress_hooks": [progress_hook],
        # فشرده‌سازی با ffmpeg
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            },
        ],
        # محدود کردن کیفیت
        "postprocessor_args": [
            "-vf",
            "scale=-2:480",  # اجبار به 480p
            "-c:v",
            "libx264",
            "-crf",
            "28",  # فشرده‌سازی بیشتر (23-28 خوبه)
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-b:a",
            "96k",  # کیفیت صدا پایین‌تر
        ],
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

                # اگه هنوز بزرگه، بیشتر فشرده کن
                if file_size > MAX_TG_VIDEO_SIZE:
                    print(f"⚠️ File too large, compressing more...")
                    compressed_file = compress_video_more(final_file)
                    if compressed_file:
                        os.remove(final_file)
                        return compressed_file

                return os.path.abspath(final_file)

            # فال‌بک
            all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
            print(f"📂 All files in download dir: {all_files}")

            if all_files:
                latest = max(all_files, key=os.path.getctime)
                print(f"⚠️ Using latest file: {latest}")

                file_size = os.path.getsize(latest)
                if file_size > MAX_TG_VIDEO_SIZE:
                    print(f"⚠️ File too large, compressing more...")
                    compressed_file = compress_video_more(latest)
                    if compressed_file:
                        os.remove(latest)
                        return compressed_file

                return os.path.abspath(latest)

            print("❌ No file found!")
            return None

    except Exception as e:
        print(f"❌ Error downloading YT Video: {e}")
        import traceback

        traceback.print_exc()
        return None


def compress_video_more(input_file):
    """فشرده‌سازی بیشتر ویدیو با ffmpeg"""
    try:
        import subprocess

        output_file = input_file.replace(".mp4", "_compressed.mp4")

        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-vf",
            "scale=-2:480",
            "-c:v",
            "libx264",
            "-crf",
            "32",  # فشرده‌سازی خیلی بیشتر
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "64k",  # کیفیت صدا خیلی پایین
            "-y",
            output_file,
        ]

        print(f"🔧 Compressing with ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0 and os.path.exists(output_file):
            new_size = os.path.getsize(output_file)
            print(f"✅ Compressed to: {new_size / (1024 * 1024):.2f} MB")
            return output_file
        else:
            print(f"❌ Compression failed: {result.stderr}")
            return None

    except Exception as e:
        print(f"❌ Compression error: {e}")
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

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            mp3_files = [f for f in files if f.endswith(".mp3")]

            print(f"🔎 Found files: {files}")
            print(f"🎵 MP3 files: {mp3_files}")

            if mp3_files:
                return os.path.abspath(mp3_files[0]), title, performer

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
