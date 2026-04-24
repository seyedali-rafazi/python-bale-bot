# services/youtube.py

import os
import glob
import yt_dlp
import uuid
import subprocess
import math
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DOWNLOAD_SIZE = 300 * 1024 * 1024
SPLIT_SIZE_LIMIT = 20 * 1024 * 1024


def get_video_duration(file_path):
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        output = subprocess.check_output(cmd, text=True)
        return float(output.strip())
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0


def split_video_if_needed(file_path):
    file_size = os.path.getsize(file_path)
    if file_size <= SPLIT_SIZE_LIMIT:
        return [file_path]

    duration = get_video_duration(file_path)
    if not duration:
        return [file_path]

    safe_split_size = 15 * 1024 * 1024
    num_chunks = math.ceil(file_size / safe_split_size)
    segment_time = duration / num_chunks

    base_name, ext = os.path.splitext(file_path)
    output_pattern = f"{base_name}_part%03d{ext}"

    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(segment_time),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]

    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        os.remove(file_path)
        parts = sorted(glob.glob(f"{base_name}_part*{ext}"))
        return parts
    except Exception as e:
        print(f"Error splitting video: {e}")
        return [file_path]


def progress_hook(d, progress_dict):
    """به‌روزرسانی درصد دانلود در دیکشنری مشترک"""
    if progress_dict is None:
        return

    if d["status"] == "downloading":
        percent = d.get("_percent_str", "N/A").strip()
        speed = d.get("_speed_str", "N/A").strip()
        eta = d.get("_eta_str", "N/A").strip()
        progress_dict["text"] = (
            f"📥 در حال دانلود: {percent}\n🚀 سرعت: {speed}\n⏳ زمان باقیمانده: {eta}"
        )
    elif d["status"] == "finished":
        progress_dict["text"] = "✅ دانلود تکمیل شد! در حال آماده‌سازی فایل..."


def download_youtube_video(url, progress_dict=None):
    req_id = uuid.uuid4().hex

    def my_hook(d):
        progress_hook(d, progress_dict)

    ydl_opts = {
        "proxy": PROXY,
        "format": "best[height<=720][filesize<300M]/best[height<=480][filesize<300M]/best[height<=360]/worst",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [my_hook] if progress_dict else [],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get("filesize") or info.get("filesize_approx") or 0

            if filesize > MAX_DOWNLOAD_SIZE:
                return "TOO_LARGE"

            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.*")
            files = glob.glob(pattern)

            if not files:
                return None

            final_file = files[0]
            actual_size = os.path.getsize(final_file)

            if actual_size > MAX_DOWNLOAD_SIZE:
                os.remove(final_file)
                return "TOO_LARGE"

            return split_video_if_needed(final_file)

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def download_youtube_audio(url, progress_dict=None):
    req_id = uuid.uuid4().hex

    def my_hook(d):
        progress_hook(d, progress_dict)

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
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "progress_hooks": [my_hook] if progress_dict else [],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            title = info.get("title", "Unknown Title")
            performer = info.get("uploader", "Unknown Artist")
            video_id = info.get("id", "unknown")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.*")
            files = glob.glob(pattern)
            mp3_files = [f for f in files if f.endswith(".mp3")]

            if mp3_files:
                return os.path.abspath(mp3_files[0]), title, performer

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
