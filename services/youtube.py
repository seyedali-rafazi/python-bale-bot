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

# محدودیت‌های جدید حجم
MAX_DOWNLOAD_SIZE = 300 * 1024 * 1024  # 300 مگابایت
SPLIT_SIZE_LIMIT = 45 * 1024 * 1024  # 45 مگابایت


def get_video_duration(file_path):
    """دریافت زمان کل ویدیو با استفاده از ffprobe"""
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
    # حداکثر حجم مجاز بله 48 در نظر گرفته می‌شود تا حاشیه امن باشد
    max_bale_size = 48 * 1024 * 1024
    target_size = 35 * 1024 * 1024  # هدف 35 مگابایت

    file_size = os.path.getsize(file_path)
    if file_size <= max_bale_size:
        return [file_path]

    duration = get_video_duration(file_path)
    if not duration:
        return [file_path]

    # محاسبه زمان و تعداد پارت‌ها
    chunks = math.ceil(file_size / target_size)
    segment_time = math.ceil(duration / chunks)

    # --- محاسبه دقیق بیت‌ریت (Bitrate) ---
    # تبدیل حجم هدف به بیت و تقسیم بر زمان هر پارت (bps)
    target_size_bits = target_size * 8
    max_rate_bps = int(target_size_bits / segment_time)

    base_name, ext = os.path.splitext(file_path)
    output_pattern = f"{base_name}_part%03d{ext}"

    # پارامترهای کنترل حجم به ffmpeg اضافه شدند
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        file_path,
        "-force_key_frames",
        f"expr:gte(t,n_forced*{segment_time})",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        str(max_rate_bps),  # تنظیم بیت‌ریت هدف
        "-maxrate",
        str(max_rate_bps),  # جلوگیری قطعی از افزایش حجم در صحنه‌های شلوغ
        "-bufsize",
        str(max_rate_bps * 2),  # بافر استاندارد
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "segment",
        "-segment_time",
        str(segment_time),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]

    try:
        print(
            f"⏳ Splitting video into ~{chunks} parts with maxrate {max_rate_bps} bps..."
        )
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error: {e}")
        return [file_path]

    parts = sorted(glob.glob(f"{base_name}_part*{ext}"))

    valid_parts = []
    for part in parts:
        if os.path.getsize(part) > (49 * 1024 * 1024):
            os.remove(part)  # اگر باز هم استثنائاً بزرگتر بود حذف شود که ربات کرش نکند
        else:
            valid_parts.append(part)

    return valid_parts


def download_youtube_video(url):
    """دانلود ویدیو - تا سقف 300 مگابایت با پشتیبانی از چند کاربر همزمان"""

    # تولید یک شناسه یکتا برای جلوگیری از تداخل دانلود کاربران
    req_id = uuid.uuid4().hex

    ydl_opts = {
        "proxy": PROXY,
        "format": "best[height<=720][filesize<300M]/best[height<=480][filesize<300M]/best[height<=360]/worst",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s"),
        "quiet": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # فقط اطلاعات بگیر، دانلود نکن
            info = ydl.extract_info(url, download=False)
            filesize = info.get("filesize") or info.get("filesize_approx") or 0
            size_mb = filesize / (1024 * 1024)

            if filesize > MAX_DOWNLOAD_SIZE:
                print(f"❌ Too large: {size_mb:.1f} MB")
                return "TOO_LARGE"

            # سایز اوکیه، دانلود کن
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")

            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.*")
            files = glob.glob(pattern)

            if not files:
                return None

            final_file = files[0]
            actual_size = os.path.getsize(final_file)

            # چک نهایی بعد دانلود
            if actual_size > MAX_DOWNLOAD_SIZE:
                os.remove(final_file)
                return "TOO_LARGE"

            # تقسیم در صورت نیاز و بازگرداندن لیست فایل‌ها
            return split_video_if_needed(final_file)

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def download_youtube_audio(url):
    # این متد را برای جلوگیری از تداخل کاربران با UUID اصلاح کردیم
    req_id = uuid.uuid4().hex
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
