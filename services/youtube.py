# services/youtube.py

import os
import glob
import uuid
import math
import asyncio
import logging
import subprocess
import shutil
import sys
import threading
import time
from collections import deque
from functools import lru_cache
from dotenv import load_dotenv
import random
import json
import re

load_dotenv()
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
COOKIE_FILE = os.getenv("YTDLP_COOKIE_FILE", "cookies.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DOWNLOAD_SIZE = 1 * 1024 * 1024 * 1024
MAX_TELEGRAM_DOWNLOAD_SIZE = 1 * 1024 * 1024 * 1024
SPLIT_SIZE_LIMIT = 50 * 1024 * 1024

IPV6_PREFIX = os.getenv("IPV6_PREFIX")
ENABLE_IPV6_ROTATION = os.getenv("ENABLE_IPV6_ROTATION", "false").lower() in ("true", "1", "yes")
# Optional IPv6: set USE_IPV6=true to force IPv6 (default: IPv4)
USE_IPV6 = os.getenv("USE_IPV6", "false").lower() in ("true", "1", "yes")
IP_FORCE_FLAG = "--force-ipv6" if USE_IPV6 else "--force-ipv4"


def get_random_ipv6():
    """تولید یک آی‌پی تصادفی از ساب‌نت /64 در صورت فعال بودن"""
    if not IPV6_PREFIX:
        return None
    clean_prefix = IPV6_PREFIX.split("/")[0].rstrip(":")
    hextets = [f"{random.randint(0, 65535):x}" for _ in range(4)]
    suffix = ":".join(hextets)
    return f"{clean_prefix}:{suffix}"


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
        output = subprocess.check_output(cmd, text=True, timeout=20)
        return float(output.strip())
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0


_cookie_cache_checked_at: float = 0.0
_cookie_cache_exists: bool = False
_cookie_warned_missing: bool = False


def _cookie_args():
    global _cookie_cache_checked_at, _cookie_cache_exists, _cookie_warned_missing
    if not COOKIE_FILE:
        return []
    now = time.monotonic()
    if now - _cookie_cache_checked_at > 60.0:
        _cookie_cache_exists = os.path.exists(COOKIE_FILE)
        _cookie_cache_checked_at = now
        if not _cookie_cache_exists and not _cookie_warned_missing:
            print(f"Cookie file not found: {COOKIE_FILE}")
            _cookie_warned_missing = True
    if _cookie_cache_exists:
        return ["--cookies", COOKIE_FILE]
    return []


@lru_cache(maxsize=1)
def _cached_ytdlp_executable() -> tuple[str, ...]:
    which = shutil.which("yt-dlp")
    if which:
        return (which,)
    venv_dir = os.path.dirname(sys.executable)
    for name in ("yt-dlp.exe", "yt-dlp"):
        candidate = os.path.join(venv_dir, name)
        if os.path.exists(candidate):
            return (candidate,)
    return (sys.executable, "-m", "yt_dlp")


def get_ytdlp_executable() -> list[str]:
    return list(_cached_ytdlp_executable())


def get_base_search_cmd() -> list[str]:
    cmd = list(get_ytdlp_executable())
    cmd.extend(
        [
            IP_FORCE_FLAG,
            "--socket-timeout",
            "15",
        ]
    )

    if USE_IPV6 and ENABLE_IPV6_ROTATION and IPV6_PREFIX:
        random_ip = get_random_ipv6()
        if random_ip:
            cmd.extend(["--source-address", random_ip])

    cmd.extend(_cookie_args())
    return cmd


def _base_ytdlp_cmd():
    cmd = list(get_ytdlp_executable())
    cmd.extend(
        [
            IP_FORCE_FLAG,
        ]
    )

    # Only use --source-address if IPv6 is enabled and rotation is explicitly enabled
    if USE_IPV6 and ENABLE_IPV6_ROTATION and IPV6_PREFIX:
        random_ip = get_random_ipv6()
        if random_ip:
            logger.debug("Using Random IPv6: %s", random_ip)
            cmd.extend(["--source-address", random_ip])

    cmd.extend(
        [
            "--socket-timeout",
            "20",
            "--js-runtimes",
            "node",
            "--remote-components",
            "ejs:github",
            "--extractor-args",
            "youtube:player_client=android_embed,web_embedded",
            "--no-playlist",
        ]
    )

    cmd.extend(_cookie_args())

    return cmd


def generate_progress_bar(percent: float, length: int = 10) -> str:
    filled = int((percent / 100) * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percent:.1f}%"


_YT_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|youtube\.com/(?:shorts|live|embed)/|^)([0-9A-Za-z_-]{11})(?:[?&/#]|$)"
)


def extract_yt_id_fast(url: str) -> str | None:
    """Extract 11-character YouTube video ID from common URLs without spawning yt-dlp."""
    if not url:
        return None
    m = _YT_ID_RE.search(url.strip())
    return m.group(1) if m else None


def _format_bytes_estimate(fmt: dict, duration: float | int | None) -> int | None:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if isinstance(size, (int, float)) and size > 0:
        return int(size)
    tbr = fmt.get("tbr") or fmt.get("abr") or fmt.get("vbr")
    if isinstance(tbr, (int, float)) and tbr > 0 and isinstance(duration, (int, float)) and duration > 0:
        return int((tbr * 1000.0 / 8.0) * float(duration))
    return None


def _estimate_format_sizes_from_formats(formats: list, duration: float | int | None) -> dict[str, int]:
    """Estimate total bytes per common quality selector from yt-dlp --dump-json formats."""
    if not isinstance(formats, list) or not formats:
        return {}

    audio_only = [
        f for f in formats
        if isinstance(f, dict)
        and f.get("acodec") not in (None, "none")
        and f.get("vcodec") in (None, "none")
    ]
    best_audio_size: int | None = None
    best_audio_score = (-1, -1.0)
    for af in audio_only:
        sz = _format_bytes_estimate(af, duration)
        if not sz:
            continue
        is_m4a = 1 if af.get("ext") == "m4a" else 0
        abr = float(af.get("abr") or af.get("tbr") or 0)
        score = (is_m4a, abr)
        if score > best_audio_score:
            best_audio_score = score
            best_audio_size = sz

    sizes: dict[str, int] = {}
    if best_audio_size:
        sizes["bestaudio"] = best_audio_size

    for q_str in ("360", "480", "720", "1080"):
        max_h = int(q_str)
        best_video_only: int | None = None
        best_vo_score = (-1, -1, -1.0)
        best_muxed: int | None = None
        best_mx_score = (-1, -1.0)

        for vf in formats:
            if not isinstance(vf, dict):
                continue
            h = vf.get("height")
            if not isinstance(h, (int, float)) or h <= 0 or h > max_h:
                continue
            vcodec = vf.get("vcodec")
            acodec = vf.get("acodec")
            if vcodec in (None, "none"):
                continue
            sz = _format_bytes_estimate(vf, duration)
            if not sz:
                continue
            if acodec in (None, "none"):
                is_mp4 = 1 if vf.get("ext") == "mp4" else 0
                score = (int(h), is_mp4, float(vf.get("tbr") or 0))
                if score > best_vo_score:
                    best_vo_score = score
                    best_video_only = sz
            else:
                score = (int(h), float(vf.get("tbr") or 0))
                if score > best_mx_score:
                    best_mx_score = score
                    best_muxed = sz

        if best_video_only and best_audio_size:
            sizes[q_str] = best_video_only + best_audio_size
        elif best_muxed:
            sizes[q_str] = best_muxed

    return sizes


def _extract_info_dict(data: dict) -> dict:
    return {
        "title": data.get("title", "بدون عنوان"),
        "thumbnail": data.get("thumbnail"),
        "duration": data.get("duration", 0),
        "uploader": data.get("uploader") or data.get("channel") or "ناشناس",
        "channel": data.get("channel"),
        "channel_id": data.get("channel_id"),
        "uploader_id": data.get("channel_id") or data.get("uploader_id"),
        "channel_url": data.get("channel_url") or data.get("uploader_url"),
        "uploader_url": data.get("uploader_url"),
        "upload_date": data.get("upload_date"),
        "timestamp": data.get("timestamp") or data.get("release_timestamp"),
    }


def _parse_video_info_json(raw_stdout: str) -> dict | None:
    data = json.loads(raw_stdout)
    return _extract_info_dict(data)


def _parse_video_info_and_sizes_json(raw_stdout: str) -> tuple[dict | None, dict[str, int]]:
    data = json.loads(raw_stdout)
    info = _extract_info_dict(data)
    sizes = _estimate_format_sizes_from_formats(
        data.get("formats") or [],
        data.get("duration"),
    )
    return info, sizes


def _normalize_format_selector(format_selector) -> str:
    if isinstance(format_selector, str) and format_selector.isdigit():
        quality = format_selector
        if quality == "720":
            return "136+140/bestvideo[height<=720]+bestaudio/best[height<=720]"
        if quality == "480":
            return "135+140/bestvideo[height<=480]+bestaudio/best[height<=480]"
        if quality == "360":
            return "134+140/bestvideo[height<=360]+bestaudio/best[height<=360]"
        return (
            f"bv*[height<={quality}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={quality}]+ba/"
            f"b[height<={quality}]"
        )
    return str(format_selector)


def _parse_filesize_stdout(stdout_text: str) -> int | None:
    lines = [x.strip() for x in stdout_text.splitlines() if x.strip()]
    if not lines:
        return None
    size_text = lines[-1].strip()
    if size_text.upper() in {"NA", "N/A", "NONE"}:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", size_text)
    if not match:
        return None
    size = int(float(match.group(1)))
    logger.debug("Estimated size: %.2f MB", size / (1024 * 1024))
    return size


async def _run_async_subprocess(
    cmd: list[str],
    timeout_sec: float = 60.0,
) -> tuple[int, str, str]:
    """Run a subprocess asynchronously without occupying ThreadPoolExecutor slots."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_sec,
        )
        return (
            proc.returncode if proc.returncode is not None else -1,
            stdout_b.decode("utf-8", errors="replace") if stdout_b else "",
            stderr_b.decode("utf-8", errors="replace") if stderr_b else "",
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise


_inflight_info: dict[str, asyncio.Task] = {}
_inflight_size: dict[str, asyncio.Task] = {}
_inflight_search: dict[str, asyncio.Task] = {}
_YTDLP_INFO_SEMAPHORE = asyncio.Semaphore(max(2, int(os.getenv("YTDLP_INFO_CONCURRENT", "6"))))
_YTDLP_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(max(2, int(os.getenv("YTDLP_DOWNLOAD_CONCURRENT", "6"))))
_FFMPEG_SPLIT_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("FFMPEG_SPLIT_CONCURRENT", "2"))))


async def async_get_video_duration(file_path: str) -> float:
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
    try:
        rc, out, _ = await _run_async_subprocess(cmd, timeout_sec=20.0)
        if rc == 0 and out.strip():
            return float(out.strip())
    except Exception as e:
        print(f"Error getting duration: {e}")
    return 0


def _filesize_cache_key(vid: str, format_selector: str) -> str:
    import hashlib

    sel_hash = hashlib.md5(str(format_selector).encode("utf-8")).hexdigest()[:12]
    return f"yt_size:{vid}:{sel_hash}"


async def _async_get_video_info_with_sizes(url: str) -> tuple[dict | None, dict[str, int]]:
    cmd = _base_ytdlp_cmd()
    cmd.extend(["--dump-json", "--skip-download", url])
    try:
        async with _YTDLP_INFO_SEMAPHORE:
            rc, out, _ = await _run_async_subprocess(cmd, timeout_sec=60.0)
        if rc == 0 and out.strip():
            return _parse_video_info_and_sizes_json(out)
    except Exception as e:
        logger.warning("Error getting video info: %s", e)
    return None, {}


async def async_get_video_info(url: str) -> dict | None:
    info, _ = await _async_get_video_info_with_sizes(url)
    return info


async def async_get_video_filesize(
    url: str,
    format_selector="best[height<=480][ext=mp4]/best[height<=480]/best",
) -> int | None:
    selector = _normalize_format_selector(format_selector)
    cmd = _base_ytdlp_cmd()
    cmd.extend(["-f", selector, "--print", "%(filesize,filesize_approx)s", "--skip-download", url])
    try:
        async with _YTDLP_INFO_SEMAPHORE:
            rc, out, err = await _run_async_subprocess(cmd, timeout_sec=60.0)
        if rc != 0:
            logger.warning("Failed getting filesize: %s", err[:250])
            return None
        return _parse_filesize_stdout(out)
    except Exception as e:
        logger.warning("Error getting filesize: %s", e)
        return None


async def get_video_info_cached(url: str) -> dict | None:
    """Fetch YouTube video info with 6-hour Redis/memory caching and shielded singleflight dedup."""
    from services.cache_service import cache_get, cache_set, cache_set_many

    vid = extract_yt_id_fast(url)
    cache_key = f"yt_info:{vid}" if vid else None
    if cache_key:
        cached = await cache_get(cache_key)
        if isinstance(cached, dict) and cached.get("title"):
            return cached

    async def _fetch():
        format_sizes: dict[str, int] = {}
        if get_video_info is not _ORIG_GET_VIDEO_INFO:
            info = await asyncio.to_thread(get_video_info, url)
        elif async_get_video_info is not _ORIG_ASYNC_GET_VIDEO_INFO:
            info = await async_get_video_info(url)
        else:
            info, format_sizes = await _async_get_video_info_with_sizes(url)

        if info and cache_key:
            await cache_set(cache_key, info, ttl_sec=21600)
            if vid and format_sizes:
                size_items = {
                    _filesize_cache_key(vid, sel): int(sz)
                    for sel, sz in format_sizes.items()
                    if sz > 0
                }
                if size_items:
                    await cache_set_many(size_items, ttl_sec=3600)
        return info

    if not cache_key:
        return await _fetch()

    existing = _inflight_info.get(cache_key)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    task = asyncio.create_task(_fetch())
    _inflight_info[cache_key] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _inflight_info.get(cache_key) is done_task:
            _inflight_info.pop(cache_key, None)
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)


async def get_video_filesize_cached(
    url: str,
    format_selector: str = "best[height<=480][ext=mp4]/best[height<=480]/best",
) -> int | None:
    """Fetch estimated filesize with 1-hour Redis/memory caching and shielded singleflight dedup."""
    from services.cache_service import cache_get, cache_set

    vid = extract_yt_id_fast(url)
    cache_key = _filesize_cache_key(vid, format_selector) if vid else None
    if cache_key:
        cached = await cache_get(cache_key)
        if isinstance(cached, int) and cached > 0:
            return cached

    async def _fetch():
        if get_video_filesize is not _ORIG_GET_VIDEO_FILESIZE:
            size = await asyncio.to_thread(get_video_filesize, url, format_selector)
        else:
            size = await async_get_video_filesize(url, format_selector)
        if size and cache_key:
            await cache_set(cache_key, int(size), ttl_sec=3600)
        return size

    if not cache_key:
        return await _fetch()

    existing = _inflight_size.get(cache_key)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    task = asyncio.create_task(_fetch())
    _inflight_size[cache_key] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _inflight_size.get(cache_key) is done_task:
            _inflight_size.pop(cache_key, None)
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)


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
                "uploader": data.get("uploader") or data.get("channel") or "ناشناس",
                "channel": data.get("channel"),
                "channel_id": data.get("channel_id"),
                "uploader_id": data.get("channel_id") or data.get("uploader_id"),
                "channel_url": data.get("channel_url") or data.get("uploader_url"),
                "uploader_url": data.get("uploader_url"),
                "upload_date": data.get("upload_date"),
                "timestamp": data.get("timestamp") or data.get("release_timestamp"),
            }

    except Exception as e:
        print(f"Error getting video info: {e}")

    return None


def uploaded_at_from_video_info(info: dict | None) -> str | None:
    """Sortable publish time from yt-dlp (YouTube channel upload, not bot cache)."""
    if not info:
        return None
    ts = info.get("timestamp") or info.get("release_timestamp")
    if ts is not None:
        try:
            from datetime import datetime, timezone

            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
                "%Y%m%d%H%M%S"
            )
        except (ValueError, OSError, TypeError):
            pass
    upload_date = info.get("upload_date")
    if upload_date:
        s = str(upload_date).strip()
        if len(s) >= 8 and s[:8].isdigit():
            return s[:8]
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


YTDLP_DOWNLOAD_TIMEOUT_SEC = max(
    60, int(os.getenv("YTDLP_DOWNLOAD_TIMEOUT_SEC", "900"))
)


async def _run_async_subprocess_and_capture(
    cmd: list[str],
    progress_dict=None,
    timeout_sec: int = YTDLP_DOWNLOAD_TIMEOUT_SEC,
) -> tuple[bool, str]:
    """Run yt-dlp asynchronously with live progress parsing and zero ThreadPool usage."""
    logger.debug("Running yt-dlp command: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output_lines: deque[str] = deque(maxlen=200)

    async def _pump_and_wait() -> int:
        if proc.stdout is not None:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                output_lines.append(line)
                if progress_dict is not None:
                    if "[download]" in line and "%" in line:
                        match = re.search(r"(\d+\.\d+)%", line)
                        if match:
                            percent = float(match.group(1))
                            bar = generate_progress_bar(percent)
                            clean_line = line.split("]", 1)[-1].strip()
                            progress_dict["text"] = (
                                f"📥 در حال دانلود...\n{bar}\n{clean_line}"
                            )
                    elif "Destination:" in line:
                        progress_dict["text"] = "📥 شروع دانلود..."
                        logger.debug("%s", line)
                elif not line.startswith("[download]"):
                    logger.debug("%s", line)
        return await proc.wait()

    timed_out = False
    try:
        rc = await asyncio.wait_for(_pump_and_wait(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        rc = -1
    except asyncio.CancelledError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise

    full_output = "\n".join(output_lines)
    if timed_out:
        logger.warning("yt-dlp timed out after %ss", timeout_sec)
        return False, f"{full_output}\nTimed out after {timeout_sec}s".strip()
    if rc != 0:
        logger.warning("yt-dlp failed (rc=%s): %s", rc, full_output[-400:])
        return False, full_output
    return True, full_output


def _run_subprocess_and_capture(
    cmd,
    progress_dict=None,
    timeout_sec: int = YTDLP_DOWNLOAD_TIMEOUT_SEC,
):
    print("Running command:")
    print(" ".join(cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    timed_out = False

    def _on_timeout():
        nonlocal timed_out
        timed_out = True
        try:
            process.kill()
        except Exception:
            pass

    timer = threading.Timer(timeout_sec, _on_timeout)
    timer.daemon = True
    timer.start()

    output_lines: deque[str] = deque(maxlen=200)
    try:
        if process.stdout is not None:
            for line in process.stdout:
                line = line.rstrip()
                output_lines.append(line)

                if progress_dict is not None:
                    if "[download]" in line and "%" in line:
                        match = re.search(r"(\d+\.\d+)%", line)

                        if match:
                            percent = float(match.group(1))
                            bar = generate_progress_bar(percent)

                            clean_line = line.split("]", 1)[-1].strip()

                            progress_dict["text"] = (
                                f"📥 در حال دانلود...\n{bar}\n{clean_line}"
                            )

                    elif "Destination:" in line:
                        progress_dict["text"] = "📥 شروع دانلود..."
                        print(line)
                elif not line.startswith("[download]"):
                    print(line)

        process.wait()
    finally:
        timer.cancel()
        if process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass
        if process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass

    full_output = "\n".join(output_lines)

    if timed_out:
        print(f"❌ yt-dlp timed out after {timeout_sec}s")
        return False, f"{full_output}\nTimed out after {timeout_sec}s".strip()

    if process.returncode != 0:
        print("❌ yt-dlp failed")
        print(full_output)
        return False, full_output

    return True, full_output


def _find_downloaded_file(video_id, req_id, preferred_ext=None):
    prefix = video_id or "*"
    if preferred_ext:
        pattern = os.path.join(DOWNLOAD_DIR, f"{prefix}_{req_id}.{preferred_ext}")
        files = glob.glob(pattern)

        if files:
            return files[0]

    pattern = os.path.join(DOWNLOAD_DIR, f"{prefix}_{req_id}.*")

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
    HARD_LIMIT = 45 * 1024 * 1024

    if await asyncio.to_thread(os.path.getsize, original_file_path) <= HARD_LIMIT:
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

        file_size = await asyncio.to_thread(os.path.getsize, current_file)
        if file_size <= HARD_LIMIT:
            final_valid_parts.append(current_file)
            continue

        duration = await async_get_video_duration(current_file)

        if not duration or duration <= 0:
            final_valid_parts.append(current_file)
            continue

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

        part_glob = f"{base_name}_temp_{part_counter - 1}_*{ext}"

        def _cleanup_glob(pattern: str) -> None:
            for p in glob.glob(pattern):
                if p != original_file_path:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        try:
            async with _FFMPEG_SPLIT_SEMAPHORE:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )

                try:
                    await asyncio.wait_for(process.communicate(), timeout=300)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                        await process.wait()
                    except Exception:
                        pass
                    await asyncio.to_thread(_cleanup_glob, part_glob)
                    raise RuntimeError("ffmpeg segment timed out")
                except asyncio.CancelledError:
                    try:
                        process.kill()
                        await process.wait()
                    except Exception:
                        pass
                    await asyncio.to_thread(_cleanup_glob, part_glob)
                    raise

            if process.returncode == 0:
                new_parts = await asyncio.to_thread(
                    lambda p=part_glob: sorted(glob.glob(p))
                )

                # Guard against infinite loop when keyframe spacing prevents splitting into smaller parts
                if not new_parts:
                    final_valid_parts.append(current_file)
                    continue
                if len(new_parts) == 1:
                    only_size = await asyncio.to_thread(os.path.getsize, new_parts[0])
                    if only_size >= file_size * 0.95:
                        if new_parts[0] != current_file and await asyncio.to_thread(os.path.exists, new_parts[0]):
                            await asyncio.to_thread(os.remove, new_parts[0])
                        final_valid_parts.append(current_file)
                        continue

                files_to_process = new_parts + files_to_process

                if current_file != original_file_path and await asyncio.to_thread(os.path.exists, current_file):
                    await asyncio.to_thread(os.remove, current_file)

            else:
                await asyncio.to_thread(_cleanup_glob, part_glob)
                final_valid_parts.append(current_file)

        except asyncio.CancelledError:
            await asyncio.to_thread(_cleanup_glob, f"{base_name}_temp_*{ext}")
            raise
        except Exception as e:
            print(f"Error in ffmpeg: {e}")
            await asyncio.to_thread(_cleanup_glob, part_glob)
            final_valid_parts.append(current_file)

    if original_file_path not in final_valid_parts and await asyncio.to_thread(
        os.path.exists, original_file_path
    ):
        await asyncio.to_thread(os.remove, original_file_path)

    return final_valid_parts


def download_youtube_video(
    url, quality="480", progress_dict=None, max_filesize=MAX_DOWNLOAD_SIZE
):
    req_id = uuid.uuid4().hex

    video_id = extract_yt_id_fast(url) or _get_video_id_by_ytdlp(url)

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

    video_id = extract_yt_id_fast(url) or _get_video_id_by_ytdlp(url)

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


async def async_download_youtube_video(
    url: str,
    quality: str = "480",
    progress_dict=None,
    max_filesize: int = MAX_DOWNLOAD_SIZE,
):
    """Native async YouTube video download without occupying ThreadPoolExecutor slots."""
    req_id = uuid.uuid4().hex
    video_id = extract_yt_id_fast(url)

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s")
    format_selector = _normalize_format_selector(str(quality))
    cmd = _base_ytdlp_cmd()
    cmd.extend(
        [
            "--newline",
            "-f",
            format_selector,
            "--merge-output-format",
            "mp4",
            "--max-filesize",
            str(max_filesize),
            "-o",
            output_template,
            url,
        ]
    )

    def _cleanup_req_files() -> None:
        for p in glob.glob(os.path.join(DOWNLOAD_DIR, f"*_{req_id}*")):
            try:
                os.remove(p)
            except OSError:
                pass

    try:
        async with _YTDLP_DOWNLOAD_SEMAPHORE:
            ok, output = await _run_async_subprocess_and_capture(cmd, progress_dict=progress_dict)
    except BaseException:
        await asyncio.to_thread(_cleanup_req_files)
        raise

    if not ok:
        await asyncio.to_thread(_cleanup_req_files)
        if "File is larger than max-filesize" in output or "max-filesize" in output:
            return "TOO_LARGE"
        return None

    final_file = await asyncio.to_thread(_find_downloaded_file, video_id, req_id)
    if not final_file or not await asyncio.to_thread(os.path.exists, final_file):
        logger.warning("YouTube video download finished but file not found (req_id=%s)", req_id)
        return None

    actual_size = await asyncio.to_thread(os.path.getsize, final_file)
    if actual_size > max_filesize:
        try:
            await asyncio.to_thread(os.remove, final_file)
        except Exception:
            pass
        return "TOO_LARGE"

    return final_file


async def async_download_youtube_audio(
    video_id_or_url: str,
    max_filesize: int = MAX_DOWNLOAD_SIZE,
):
    """Native async YouTube audio download without occupying ThreadPoolExecutor slots."""
    if video_id_or_url.startswith("http://") or video_id_or_url.startswith("https://"):
        url = video_id_or_url
    else:
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"

    req_id = uuid.uuid4().hex
    video_id = extract_yt_id_fast(url)

    output_template = os.path.join(DOWNLOAD_DIR, f"%(id)s_{req_id}.%(ext)s")
    cmd = _base_ytdlp_cmd()
    cmd.extend(
        [
            "--newline",
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

    def _cleanup_audio_req_files() -> None:
        for p in glob.glob(os.path.join(DOWNLOAD_DIR, f"*_{req_id}*")):
            try:
                os.remove(p)
            except OSError:
                pass

    try:
        async with _YTDLP_DOWNLOAD_SEMAPHORE:
            ok, output = await _run_async_subprocess_and_capture(cmd)
    except BaseException:
        await asyncio.to_thread(_cleanup_audio_req_files)
        raise

    if not ok:
        await asyncio.to_thread(_cleanup_audio_req_files)
        if "File is larger than max-filesize" in output or "max-filesize" in output:
            return "TOO_LARGE"
        return None

    final_file = await asyncio.to_thread(
        _find_downloaded_file, video_id, req_id, "mp3"
    )
    if not final_file or not await asyncio.to_thread(os.path.exists, final_file):
        logger.warning("Audio download finished but mp3 file not found (req_id=%s)", req_id)
        return None

    actual_size = await asyncio.to_thread(os.path.getsize, final_file)
    if actual_size > max_filesize:
        try:
            await asyncio.to_thread(os.remove, final_file)
        except Exception:
            pass
        return "TOO_LARGE"

    return final_file


def _parse_yt_search_stdout(stdout_text: str, max_results: int) -> list[dict]:
    results = []
    for line in stdout_text.splitlines():
        line = line.strip()
        if not line or "|||" not in line:
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


async def async_search_yt_videos(query: str, max_results: int = 5) -> list[dict]:
    """Async YouTube search with semaphore, shielded singleflight dedup, and 15-min cache."""
    import hashlib
    from services.cache_service import cache_get, cache_set

    clean_q = (query or "").strip()
    if not clean_q:
        return []

    q_hash = hashlib.md5(f"{clean_q.lower()}:{max_results}".encode("utf-8")).hexdigest()[:16]
    cache_key = f"yt_search:{q_hash}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list) and cached:
        return cached

    existing = _inflight_search.get(cache_key)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    async def _search() -> list[dict]:
        search_query = (
            f"ytsearch{max_results}:{clean_q}" if not clean_q.startswith("http") else clean_q
        )
        cmd = get_base_search_cmd()
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
            async with _YTDLP_INFO_SEMAPHORE:
                rc, out, err = await _run_async_subprocess(cmd, timeout_sec=45.0)
            if rc != 0:
                logger.warning("Error searching YT: %s", err[:250])
                return []
            results = _parse_yt_search_stdout(out, max_results)
            if results:
                await cache_set(cache_key, results, ttl_sec=900)
            return results
        except Exception as e:
            logger.warning("Error searching YT: %s", e)
            return []

    task = asyncio.create_task(_search())
    _inflight_search[cache_key] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _inflight_search.get(cache_key) is done_task:
            _inflight_search.pop(cache_key, None)
        if not done_task.cancelled():
            try:
                done_task.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)


_ORIG_GET_VIDEO_INFO = get_video_info
_ORIG_ASYNC_GET_VIDEO_INFO = async_get_video_info
_ORIG_GET_VIDEO_FILESIZE = get_video_filesize


def search_yt_videos(query, max_results=5):
    search_query = (
        f"ytsearch{max_results}:{query}" if not query.startswith("http") else query
    )

    cmd = get_base_search_cmd()

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
            timeout=45,
        )

        if result.returncode != 0:
            print("❌ Error searching YT:")
            print(result.stderr)
            return []

        return _parse_yt_search_stdout(result.stdout, max_results)

    except Exception as e:
        print(f"Error searching YT: {e}")
        return []
