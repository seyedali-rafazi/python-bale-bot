import os
import glob
import yt_dlp
import uuid
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# $300 \text{ MB}$ limit for total download
MAX_DOWNLOAD_SIZE = 300 * 1024 * 1024
# $45 \text{ MB}$ limit for each binary part
SPLIT_SIZE_LIMIT = 35 * 1024 * 1024


def split_file_binary(file_path):
    """تقسیم فایل به صورت باینری به تکه‌های دقیق"""
    file_size = os.path.getsize(file_path)

    if file_size <= SPLIT_SIZE_LIMIT:
        return [file_path]

    parts = []
    part_num = 1

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(SPLIT_SIZE_LIMIT)
            if not chunk:
                break

            part_name = f"{file_path}.part{part_num:03d}"
            with open(part_name, "wb") as chunk_file:
                chunk_file.write(chunk)

            parts.append(part_name)
            part_num += 1

    if os.path.exists(file_path):
        os.remove(file_path)

    return parts


def download_youtube_video(url):
    req_id = uuid.uuid4().hex
    ydl_opts = {
        "proxy": PROXY,
        "format": "best[height<=720][filesize<300M]/best[height<=480][filesize<300M]/best[height<=360]/worst",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s"),
        "quiet": False,
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

            return split_file_binary(final_file)

    except Exception as e:
        print(f"Error: {e}")
        return None


def download_youtube_audio(url):
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
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get("filesize") or info.get("filesize_approx") or 0

            if filesize > MAX_DOWNLOAD_SIZE:
                return "TOO_LARGE"

            ydl.download([url])

            pattern = os.path.join(DOWNLOAD_DIR, f"*_{req_id}.mp3")
            files = glob.glob(pattern)

            if not files:
                return None

            final_file = files[0]
            actual_size = os.path.getsize(final_file)

            if actual_size > MAX_DOWNLOAD_SIZE:
                os.remove(final_file)
                return "TOO_LARGE"

            return split_file_binary(final_file)

    except Exception as e:
        print(f"Error: {e}")
        return None


def search_yt_videos(query, max_results=5):
    ydl_opts = {
        "proxy": PROXY,
        "extract_flat": True,
        "quiet": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_query = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_query, download=False)

            if "entries" not in info:
                return []

            results = []
            for entry in info["entries"]:
                duration = entry.get("duration")
                duration_str = (
                    f"{int(duration // 60)}:{int(duration % 60):02d}"
                    if duration
                    else "نامشخص"
                )

                results.append(
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title", "بدون عنوان"),
                        "url": entry.get("url"),
                        "duration": duration_str,
                    }
                )

            return results
    except Exception as e:
        print(f"Search Error: {e}")
        return []
