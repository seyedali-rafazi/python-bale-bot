# services/youtube.py

# services/youtube.py

import os
import glob
import uuid
import math
import asyncio
import subprocess
from dotenv import load_dotenv
import random

load_dotenv()

DOWNLOAD_DIR = "downloads"
COOKIE_FILE = os.getenv("YTDLP_COOKIE_FILE", "cookies.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DOWNLOAD_SIZE = 300 * 1024 * 1024
SPLIT_SIZE_LIMIT = 20 * 1024 * 1024

IPV6_PREFIX = "2a01:4f8:c010:1e46"


def get_random_ipv6():
    """تولید یک آی‌پی تصادفی از ساب‌نت /64"""
    hextets = [f"{random.randint(0, 65535):x}" for _ in range(4)]
    suffix = ":".join(hextets)
    return f"{IPV6_PREFIX}:{suffix}"


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


def _cookie_args():
    """
    اگر فایل کوکی وجود داشته باشد، آرگومان cookies را برمی‌گرداند.
    """
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        return ["--cookies", COOKIE_FILE]

    print(f"⚠️ Cookie file not found: {COOKIE_FILE}")
    return []


# def _base_ytdlp_cmd():
#     """
#     آرگومان‌های پایه yt-dlp که روی VPS جواب داده‌اند.
#     بدون proxy، برای استفاده از مسیر شبکه خود سرور/WARP.
#     """
#     cmd = [
#         "yt-dlp",
#         # 1. اگر سرورتان IPv6 دارد، خط زیر را فعال کنید (بسیار موثر است)
#         # در غیر این صورت اگر ارور شبکه گرفتید، این خط را کامنت کنید.
#         "--force-ipv6",
#         "--js-runtimes",
#         "node",
#         "--remote-components",
#         "ejs:github",
#         # 2. تغییر کلاینت از وب به موبایل و تلویزیون برای دور زدن ربات‌گیر یوتیوب
#         "--extractor-args",
#         "youtube:client=ANDROID,IOS,TV_EMBED",
#         "--no-playlist",
#     ]

#     cmd.extend(_cookie_args())

#     return cmd


def _base_ytdlp_cmd():
    random_ip = get_random_ipv6()
    print(f"🌐 Using Random IPv6: {random_ip}")

    cmd = [
        "yt-dlp",
        "--force-ipv6",
        "--source-address",
        random_ip,
        "--js-runtimes",
        "node",
        "--remote-components",
        "ejs:github",
        "--extractor-args",
        "youtube:player_client=web",
        "--no-playlist",
    ]

    cmd.extend(_cookie_args())

    return cmd


def _run_subprocess_and_capture(cmd, progress_dict=None):
    """
    اجرای yt-dlp با subprocess.
    خروجی خط‌به‌خط خوانده می‌شود تا هم لاگ داشته باشیم، هم در صورت نیاز progress_dict آپدیت شود.
    """
    print("Running command:")
    print(" ".join(cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_lines = []

    for line in process.stdout:
        line = line.rstrip()
        output_lines.append(line)

        print(line)

        if progress_dict is not None:
            # نمونه خروجی:
            # [download]  45.3% of 6.88MiB at 1.23MiB/s ETA 00:03
            if "[download]" in line and "%" in line:
                progress_dict["text"] = f"📥 در حال دانلود...\n{line}"
            elif "Destination:" in line:
                progress_dict["text"] = "📥 شروع دانلود..."
            elif "has already been downloaded" in line:
                progress_dict["text"] = "✅ فایل از قبل دانلود شده است."
            elif "100%" in line:
                progress_dict["text"] = "✅ دانلود تکمیل شد! در حال آماده‌سازی فایل..."

    process.wait()

    full_output = "\n".join(output_lines)

    if process.returncode != 0:
        print("❌ yt-dlp failed")
        print(full_output)
        return False, full_output

    return True, full_output


def _find_downloaded_file(video_id, req_id, preferred_ext=None):
    """
    فایل دانلود شده را بر اساس id و req_id پیدا می‌کند.
    """
    if preferred_ext:
        pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.{preferred_ext}")
        files = glob.glob(pattern)
        if files:
            return files[0]

    pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.*")
    files = glob.glob(pattern)

    # فایل‌های موقت را حذف از انتخاب
    files = [
        f
        for f in files
        if not f.endswith(".part")
        and not f.endswith(".ytdl")
        and not f.endswith(".temp")
    ]

    if not files:
        return None

    # اگر چند فایل بود، بزرگ‌ترین را بردار
    files.sort(key=lambda x: os.path.getsize(x), reverse=True)
    return files[0]


def _get_video_id_by_ytdlp(url):
    """
    گرفتن video id با yt-dlp.
    برای ساخت نام فایل قابل پیش‌بینی.
    """
    cmd = _base_ytdlp_cmd()
    cmd.extend(
        [
            "--print",
            "%(id)s",
            "--skip-download",
            url,
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("❌ Failed to get video id")
            print(result.stderr)
            return None

        lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]

        if not lines:
            return None

        # آخرین خط معمولاً id است
        return lines[-1]

    except Exception as e:
        print(f"❌ Error getting video id: {e}")
        return None


async def split_video_if_needed(original_file_path):
    HARD_LIMIT = 14.5 * 1024 * 1024  # 14.5 MB

    if os.path.getsize(original_file_path) <= HARD_LIMIT:
        return [original_file_path]

    files_to_process = [original_file_path]
    final_valid_parts = []

    part_counter = 1

    base_name, ext = os.path.splitext(original_file_path)
    if ext.lower() == ".part":
        base_name, ext = os.path.splitext(base_name)
        if not ext:
            ext = ".mp4"

    while files_to_process:
        current_file = files_to_process.pop(0)

        if os.path.getsize(current_file) <= HARD_LIMIT:
            final_valid_parts.append(current_file)
            continue

        duration = get_video_duration(current_file)
        if not duration or duration <= 0:
            final_valid_parts.append(current_file)
            continue

        file_size = os.path.getsize(current_file)

        num_chunks = math.ceil(file_size / HARD_LIMIT)
        if num_chunks == 1:
            num_chunks = 2

        segment_time = duration / num_chunks

        output_pattern = f"{base_name}_temp_{part_counter}_%03d{ext}"
        part_counter += 1

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            current_file,
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
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate()

            if process.returncode == 0:
                new_parts = sorted(
                    glob.glob(f"{base_name}_temp_{part_counter - 1}_*{ext}")
                )
                # اصلاح اول: اضافه کردن پارت‌های جدید به ابتدای صف
                files_to_process = new_parts + files_to_process

                if current_file != original_file_path and os.path.exists(current_file):
                    os.remove(current_file)
            else:
                final_valid_parts.append(current_file)

        except Exception as e:
            print(f"Error in ffmpeg: {e}")
            final_valid_parts.append(current_file)

    if original_file_path not in final_valid_parts and os.path.exists(
        original_file_path
    ):
        os.remove(original_file_path)

    # اصلاح دوم: حذف sorted برای حفظ ترتیب زمانی
    return final_valid_parts


def download_youtube_video(url, progress_dict=None):
    """
    دانلود ویدیو با subprocess.
    اولویت با فرمت 18 است چون روی VPS تست شد و جواب داد.
    """
    req_id = uuid.uuid4().hex

    video_id = _get_video_id_by_ytdlp(url)
    if not video_id:
        print("❌ Could not detect video id")
        return None

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s")

    cmd = _base_ytdlp_cmd()

    cmd.extend(
        [
            "-f",
            "best[height<=480][ext=mp4]/best[height<=480]/best",
            "--max-filesize",
            str(MAX_DOWNLOAD_SIZE),
            "-o",
            output_template,
            url,
        ]
    )

    ok, output = _run_subprocess_and_capture(cmd, progress_dict=progress_dict)

    if not ok:
        if "File is larger than max-filesize" in output or "max-filesize" in output:
            return "TOO_LARGE"

        return None

    final_file = _find_downloaded_file(video_id, req_id)

    if not final_file or not os.path.exists(final_file):
        print("❌ Download finished but file not found")
        return None

    actual_size = os.path.getsize(final_file)

    if actual_size > MAX_DOWNLOAD_SIZE:
        try:
            os.remove(final_file)
        except Exception:
            pass

        return "TOO_LARGE"

    return final_file


def download_youtube_audio(video_id_or_url: str) -> str:
    """
    دانلود صدا با subprocess و تبدیل به mp3.
    """
    if video_id_or_url.startswith("http://") or video_id_or_url.startswith("https://"):
        url = video_id_or_url
    else:
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"

    req_id = uuid.uuid4().hex

    video_id = _get_video_id_by_ytdlp(url)
    if not video_id:
        print("❌ Could not detect video id")
        return None

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s")

    cmd = _base_ytdlp_cmd()

    cmd.extend(
        [
            "-f",
            "bestaudio/best",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "192K",
            "--max-filesize",
            str(MAX_DOWNLOAD_SIZE),
            "-o",
            output_template,
            url,
        ]
    )

    ok, output = _run_subprocess_and_capture(cmd)

    if not ok:
        if "File is larger than max-filesize" in output or "max-filesize" in output:
            return "TOO_LARGE"

        return None

    final_file = _find_downloaded_file(video_id, req_id, preferred_ext="mp3")

    if not final_file or not os.path.exists(final_file):
        print("❌ Audio download finished but mp3 file not found")
        return None

    actual_size = os.path.getsize(final_file)

    if actual_size > MAX_DOWNLOAD_SIZE:
        try:
            os.remove(final_file)
        except Exception:
            pass

        return "TOO_LARGE"

    return final_file


def search_yt_videos(query, max_results=5):
    """
    سرچ یوتیوب با subprocess.
    خروجی به صورت title و id گرفته می‌شود.
    """
    search_query = (
        f"ytsearch{max_results}:{query}" if not query.startswith("http") else query
    )

    cmd = _base_ytdlp_cmd()

    cmd.extend(
        [
            "--flat-playlist",
            "--print",
            "%(title)s|||%(id)s",
            "--skip-download",
            search_query,
        ]
    )

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
        )

        if result.returncode != 0:
            print("❌ Error searching YT:")
            print(result.stderr)
            return []

        results = []

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            if "|||" not in line:
                continue

            title, video_id = line.split("|||", 1)

            if video_id:
                results.append(
                    {
                        "title": title or "Unknown",
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                    }
                )

        return results[:max_results]

    except Exception as e:
        print(f"Error searching YT: {e}")
        return []
