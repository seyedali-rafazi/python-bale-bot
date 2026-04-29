# services/youtube.py

import os
import glob
import yt_dlp
import uuid
import subprocess
import math
import asyncio
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


# تبدیل به async و استفاده از asyncio.create_subprocess_exec
async def split_video_if_needed(file_path):
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
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()

        if process.returncode == 0:
            os.remove(file_path)
            parts = sorted(glob.glob(f"{base_name}_part*{ext}"))
            return parts
        return [file_path]
    except Exception as e:
        print(f"Error splitting video: {e}")
        return [file_path]


def progress_hook(d, progress_dict):
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
        "format": "best[height<=720]/best[height<=480]/best[height<=360]/worst",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "max_filesize": MAX_DOWNLOAD_SIZE,  # بهینه سازی: جلوگیری از دانلود فایل حجیم توسط خود کتابخانه
        "noplaylist": True,
        "progress_hooks": [my_hook] if progress_dict else [],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # بهینه سازی: حذف extract_info اضافه (False) و دانلود مستقیم
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.*")
            files = glob.glob(pattern)

            if not files:
                return (
                    "TOO_LARGE"  # اگر فایلی نیست، احتمالا به خاطر محدودیت حجم اسکیپ شده
                )

            final_file = files[0]
            actual_size = os.path.getsize(final_file)

            if actual_size > MAX_DOWNLOAD_SIZE:
                os.remove(final_file)
                return "TOO_LARGE"

            # تابع split حالا در هندلر صدا زده می‌شود نه اینجا
            return final_file

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def download_youtube_audio(video_id_or_url: str) -> str:
    if video_id_or_url.startswith("http://") or video_id_or_url.startswith("https://"):
        url = video_id_or_url
    else:
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"

    req_id = uuid.uuid4().hex

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"downloads/%(id)s_{req_id}.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "proxy": PROXY,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,  # بهینه سازی
        "max_filesize": MAX_DOWNLOAD_SIZE,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.mp3")
            files = glob.glob(pattern)

            if files and os.path.exists(files[0]):
                return files[0]
            else:
                return None

    except Exception as e:
        print(f"❌ Error downloading audio: {e}")
        return None


def search_yt_videos(query, max_results=5):
    ydl_opts = {
        "proxy": PROXY,
        "extract_flat": True,
        "quiet": True,
        "noplaylist": True,  # بهینه سازی: جلوگیری از لود پلی‌لیست‌ها
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
