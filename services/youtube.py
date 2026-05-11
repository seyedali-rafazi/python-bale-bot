import os
import re
import json
import uuid
import shutil
import subprocess
from pathlib import Path

DOWNLOAD_DIR = "downloads/youtube"
COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "cookies/youtube.txt")
YTDLP_BIN = os.getenv("YTDLP_BIN", "yt-dlp")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _base_ytdlp_cmd():
    cmd = [YTDLP_BIN]

    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])

    return cmd


def _safe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def get_video_precheck(url: str):
    """
    یک درخواست واحد برای دریافت:
      - title
      - thumbnail
      - uploader
      - duration
      - video_id
      - filesize / filesize_approx

    خروجی موفق:
      {
        "ok": True,
        "video_id": "...",
        "title": "...",
        "thumbnail": "...",
        "uploader": "...",
        "duration": 123,
        "size": 12345678
      }

    خروجی خطا:
      {
        "ok": False,
        "reason": "AUTH_REQUIRED|VIDEO_UNAVAILABLE|PRIVATE_VIDEO|UNKNOWN_SIZE|METADATA_FAILED|EXCEPTION",
        "message": "..."
      }
    """
    cmd = _base_ytdlp_cmd()
    cmd.extend(["--dump-json", "--skip-download", "--no-warnings", url])

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )

        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        full_error = f"{stdout_text}\n{stderr_text}".lower()

        if result.returncode != 0:
            if "sign in to confirm you're not a bot" in full_error:
                return {
                    "ok": False,
                    "reason": "AUTH_REQUIRED",
                    "message": "یوتیوب درخواست احراز هویت/کوکی داده است.",
                }

            if "cookies" in full_error:
                return {
                    "ok": False,
                    "reason": "AUTH_REQUIRED",
                    "message": "کوکی یوتیوب لازم است یا معتبر نیست.",
                }

            if "video unavailable" in full_error:
                return {
                    "ok": False,
                    "reason": "VIDEO_UNAVAILABLE",
                    "message": "ویدیو در دسترس نیست.",
                }

            if "private video" in full_error:
                return {
                    "ok": False,
                    "reason": "PRIVATE_VIDEO",
                    "message": "ویدیو خصوصی است.",
                }

            return {
                "ok": False,
                "reason": "METADATA_FAILED",
                "message": stderr_text or stdout_text or "خطا در دریافت اطلاعات ویدیو.",
            }

        data = json.loads(stdout_text)

        size = _safe_int(data.get("filesize")) or _safe_int(data.get("filesize_approx"))

        if not size:
            formats = data.get("formats") or []
            size_candidates = []

            for fmt in formats:
                fmt_size = _safe_int(fmt.get("filesize")) or _safe_int(
                    fmt.get("filesize_approx")
                )
                if fmt_size:
                    size_candidates.append(fmt_size)

            if size_candidates:
                size = max(size_candidates)

        if not size:
            return {
                "ok": False,
                "reason": "UNKNOWN_SIZE",
                "message": "حجم ویدیو قابل تشخیص نیست.",
            }

        return {
            "ok": True,
            "video_id": data.get("id"),
            "title": data.get("title") or "بدون عنوان",
            "thumbnail": data.get("thumbnail"),
            "uploader": data.get("uploader") or "نامشخص",
            "duration": _safe_int(data.get("duration")) or 0,
            "size": size,
        }

    except Exception as e:
        print(f"Error in get_video_precheck: {e}")
        return {
            "ok": False,
            "reason": "EXCEPTION",
            "message": str(e),
        }


def get_video_info(url: str):
    """
    سازگاری با کدهای قبلی؛
    اطلاعات را از precheck می‌گیرد.
    """
    result = get_video_precheck(url)
    if not result.get("ok"):
        return None

    return {
        "title": result.get("title"),
        "thumbnail": result.get("thumbnail"),
        "uploader": result.get("uploader"),
        "duration": result.get("duration"),
        "video_id": result.get("video_id"),
        "size": result.get("size"),
    }


def get_video_filesize(url: str):
    """
    سازگاری با کدهای قبلی؛
    اطلاعات را از precheck می‌گیرد.
    """
    result = get_video_precheck(url)
    if not result.get("ok"):
        return result

    return {
        "ok": True,
        "size": result.get("size"),
    }


def _extract_percent(line: str):
    match = re.search(r"(\d+(?:\.\d+)?)%", line)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return None
    return None


def _run_subprocess_and_capture(cmd, progress_dict=None):
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        collected = []

        for line in process.stdout:
            line = line.strip()
            collected.append(line)

            if progress_dict is not None:
                percent = _extract_percent(line)
                if percent is not None:
                    progress_dict["percent"] = percent

        process.wait()
        output = "\n".join(collected)

        if process.returncode != 0:
            print("❌ yt-dlp failed:")
            print(output)
            return False, output

        return True, output

    except Exception as e:
        print(f"❌ subprocess error: {e}")
        return False, str(e)


def _get_video_id_by_ytdlp(url):
    """
    گرفتن video id با yt-dlp.
    """
    cmd = _base_ytdlp_cmd()
    cmd.extend(
        [
            "--print",
            "%(id)s",
            "--skip-download",
            "--no-warnings",
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

        stderr_text = (result.stderr or "").strip().lower()
        stdout_text = (result.stdout or "").strip().lower()
        full_error = f"{stdout_text}\n{stderr_text}"

        if result.returncode != 0:
            print("❌ Failed to get video id")
            print(result.stderr)

            if "sign in to confirm you're not a bot" in full_error:
                return "AUTH_REQUIRED"

            if "cookies" in full_error:
                return "AUTH_REQUIRED"

            if "video unavailable" in full_error:
                return "VIDEO_UNAVAILABLE"

            if "private video" in full_error:
                return "PRIVATE_VIDEO"

            return None

        lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]
        if not lines:
            return None

        return lines[-1]

    except Exception as e:
        print(f"❌ Error getting video id: {e}")
        return None


def download_youtube_video(url, progress_dict=None):
    """
    دانلود ویدیو با subprocess.

    خروجی موفق:
      path_to_file

    خروجی خطا:
      TOO_LARGE
      AUTH_REQUIRED
      VIDEO_UNAVAILABLE
      PRIVATE_VIDEO
      METADATA_FAILED
      DOWNLOAD_FAILED
    """
    req_id = uuid.uuid4().hex

    video_id = _get_video_id_by_ytdlp(url)
    if not video_id:
        print("❌ Could not detect video id")
        return "METADATA_FAILED"

    if video_id in ["AUTH_REQUIRED", "VIDEO_UNAVAILABLE", "PRIVATE_VIDEO"]:
        return video_id

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s")

    cmd = _base_ytdlp_cmd()
    cmd.extend(
        [
            "-f",
            "bestvideo+bestaudio/best",
            "--merge-output-format",
            "mp4",
            "--max-filesize",
            "300M",
            "-o",
            output_template,
            "--no-playlist",
            "--newline",
            url,
        ]
    )

    ok, output = _run_subprocess_and_capture(cmd, progress_dict=progress_dict)

    if not ok:
        output_lower = (output or "").lower()

        if (
            "file is larger than max-filesize" in output_lower
            or "max-filesize" in output_lower
        ):
            return "TOO_LARGE"

        if "sign in to confirm you're not a bot" in output_lower:
            return "AUTH_REQUIRED"

        if "cookies" in output_lower:
            return "AUTH_REQUIRED"

        if "video unavailable" in output_lower:
            return "VIDEO_UNAVAILABLE"

        if "private video" in output_lower:
            return "PRIVATE_VIDEO"

        return "DOWNLOAD_FAILED"

    final_file = None
    download_path = Path(DOWNLOAD_DIR)

    for file in download_path.iterdir():
        if file.is_file() and file.stem.startswith(f"{video_id}_{req_id}"):
            final_file = str(file)
            break

    if not final_file or not os.path.exists(final_file):
        print("❌ Download finished but file not found")
        return "DOWNLOAD_FAILED"

    return final_file


def cleanup_file(file_path: str):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"cleanup_file error: {e}")


def cleanup_dir(path: str):
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        print(f"cleanup_dir error: {e}")
