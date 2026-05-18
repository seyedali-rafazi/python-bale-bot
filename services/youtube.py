# services/youtube.py

import os
import glob
import uuid
import math
import asyncio
import subprocess
from dotenv import load_dotenv
import random
import json
import re

load_dotenv()

DOWNLOAD_DIR = "downloads"
COOKIE_FILE = os.getenv("YTDLP_COOKIE_FILE", "cookies.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DOWNLOAD_SIZE = 1 * 1024 * 1024 * 1024
MAX_TELEGRAM_DOWNLOAD_SIZE = 1 * 1024 * 1024 * 1024
SPLIT_SIZE_LIMIT = 20 * 1024 * 1024

IPV6_PREFIX = os.getenv("IPV6_PREFIX")


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
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        return ["--cookies", COOKIE_FILE]

    print(f"⚠️ Cookie file not found: {COOKIE_FILE}")
    return []


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
        # "--extractor-args",
        # "youtube:player_client=android,web,ios",
        "--no-playlist",
    ]

    cmd.extend(_cookie_args())

    return cmd


def generate_progress_bar(percent: float, length: int = 10) -> str:
    filled = int((percent / 100) * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percent:.1f}%"


def get_video_info(url: str):
    cmd = _base_ytdlp_cmd()
    cmd.extend(["--dump-json", "--skip-download", url])

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)

            return {
                "title": data.get("title", "بدون عنوان"),
                "thumbnail": data.get("thumbnail"),
                "duration": data.get("duration", 0),
                "uploader": data.get("uploader", "ناشناس"),
            }

    except Exception as e:
        print(f"Error getting video info: {e}")

    return None


def get_video_filesize(
    url: str,
    format_selector="best[height<=480][ext=mp4]/best[height<=480]/best",
):
    """
    گرفتن حجم فایل قبل دانلود
    """

    if isinstance(format_selector, str) and format_selector.isdigit():
        quality = format_selector

        if quality == "720":
            format_selector = (
                "136+140/bestvideo[height<=720]+bestaudio/best[height<=720]"
            )
        elif quality == "480":
            format_selector = (
                "135+140/bestvideo[height<=480]+bestaudio/best[height<=480]"
            )
        elif quality == "360":
            format_selector = (
                "134+140/bestvideo[height<=360]+bestaudio/best[height<=360]"
            )
        else:
            format_selector = (
                f"bv*[height<={quality}][ext=mp4]+ba[ext=m4a]/"
                f"bv*[height<={quality}]+ba/"
                f"b[height<={quality}]"
            )

    cmd = _base_ytdlp_cmd()

    cmd.extend(
        [
            "-f",
            format_selector,
            "--print",
            "%(filesize,filesize_approx)s",
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
            print("❌ Failed getting filesize")
            print(result.stderr)
            return None

        lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]

        if not lines:
            return None

        size_text = lines[-1].strip()
        if size_text.upper() in {"NA", "N/A", "NONE"}:
            return None

        match = re.search(r"(\d+(?:\.\d+)?)", size_text)
        if not match:
            return None

        size = int(float(match.group(1)))

        print(f"📦 Estimated size: {size / (1024 * 1024):.2f} MB")

        return size

    except Exception as e:
        print(f"❌ Error getting filesize: {e}")
        return None


def _run_subprocess_and_capture(cmd, progress_dict=None):
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
            if "[download]" in line and "%" in line:
                match = re.search(r"(\d+\.\d+)%", line)

                if match:
                    percent = float(match.group(1))
                    bar = generate_progress_bar(percent)

                    clean_line = line.split("]", 1)[-1].strip()

                    progress_dict["text"] = f"📥 در حال دانلود...\n{bar}\n{clean_line}"

            elif "Destination:" in line:
                progress_dict["text"] = "📥 شروع دانلود..."

    process.wait()

    full_output = "\n".join(output_lines)

    if process.returncode != 0:
        print("❌ yt-dlp failed")
        print(full_output)
        return False, full_output

    return True, full_output


def _find_downloaded_file(video_id, req_id, preferred_ext=None):
    if preferred_ext:
        pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.{preferred_ext}")
        files = glob.glob(pattern)

        if files:
            return files[0]

    pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}_{req_id}.*")

    files = glob.glob(pattern)

    files = [
        f
        for f in files
        if not f.endswith(".part")
        and not f.endswith(".ytdl")
        and not f.endswith(".temp")
    ]

    if not files:
        return None

    files.sort(key=lambda x: os.path.getsize(x), reverse=True)

    return files[0]


def _get_video_id_by_ytdlp(url):
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

        return lines[-1]

    except Exception as e:
        print(f"❌ Error getting video id: {e}")
        return None


async def split_video_if_needed(original_file_path):
    HARD_LIMIT = 14.5 * 1024 * 1024

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

    return final_valid_parts


def download_youtube_video(
    url, quality="480", progress_dict=None, max_filesize=MAX_DOWNLOAD_SIZE
):
    req_id = uuid.uuid4().hex

    video_id = _get_video_id_by_ytdlp(url)

    if not video_id:
        print("❌ Could not detect video id")
        return None

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s")

    # 🎯 MAP QUALITY → EXACT GOOD COMBOS
    if str(quality) == "720":
        format_selector = "136+140/bestvideo[height<=720]+bestaudio/best[height<=720]"
    elif str(quality) == "480":
        format_selector = "135+140/bestvideo[height<=480]+bestaudio/best[height<=480]"
    elif str(quality) == "360":
        format_selector = "134+140/bestvideo[height<=360]+bestaudio/best[height<=360]"
    else:
        format_selector = (
            f"bv*[height<={quality}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={quality}]+ba/"
            f"b[height<={quality}]"
        )

    cmd = _base_ytdlp_cmd()

    cmd.extend(
        [
            "-f",
            format_selector,
            # 🔥 force proper merge like your working CLI
            "--merge-output-format",
            "mp4",
            # "--no-part",
            "--max-filesize",
            str(max_filesize),
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

    if actual_size > max_filesize:
        try:
            os.remove(final_file)
        except Exception:
            pass
        return "TOO_LARGE"

    return final_file


def download_youtube_audio(video_id_or_url: str, max_filesize=MAX_DOWNLOAD_SIZE):
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
            str(max_filesize),
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

    if actual_size > max_filesize:
        try:
            os.remove(final_file)
        except Exception:
            pass

        return "TOO_LARGE"

    return final_file


def search_yt_videos(query, max_results=5):
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
