# services/instagram.py

import asyncio
import glob
import logging
import os
import shutil
import sys
import uuid
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "ig_downloads"
COOKIES_FILE = "insta_cookies.txt"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _get_ytdlp_cmd() -> list[str]:
    which = shutil.which("yt-dlp")
    if which:
        return [which]
    venv_dir = os.path.dirname(sys.executable)
    for name in ("yt-dlp.exe", "yt-dlp"):
        candidate = os.path.join(venv_dir, name)
        if os.path.exists(candidate):
            return [candidate]
    return [sys.executable, "-m", "yt_dlp"]


def _cleanup_ig_prefix(req_id: str) -> None:
    for path in glob.glob(os.path.join(DOWNLOAD_DIR, f"{req_id}_*")):
        try:
            os.remove(path)
        except OSError:
            pass


def _find_ig_file(req_id: str) -> str | None:
    files = [
        f
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, f"{req_id}_*"))
        if not f.endswith((".part", ".ytdl", ".temp"))
    ]
    if not files:
        return None
    files.sort(key=os.path.getsize, reverse=True)
    return files[0]


async def async_download_instagram(url: str, timeout_sec: float = 60.0) -> str | None:
    """Download Instagram media via async subprocess so timeouts terminate cleanly without leaking threads/files."""
    await asyncio.to_thread(os.makedirs, DOWNLOAD_DIR, exist_ok=True)
    req_id = uuid.uuid4().hex
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{req_id}_%(id)s.%(ext)s")

    cmd = _get_ytdlp_cmd() + [
        "--quiet",
        "--no-warnings",
        "--no-playlist",
        "--sleep-interval",
        "5",
        "--max-sleep-interval",
        "15",
        "-o",
        outtmpl,
    ]
    if os.path.isfile(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])
    proxy = os.getenv("IG_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.append(url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        if proc.returncode != 0:
            err = stderr_b.decode("utf-8", errors="replace").strip() if stderr_b else ""
            logger.warning("Instagram yt-dlp failed (%s): %s", proc.returncode, err[:250])
            await asyncio.to_thread(_cleanup_ig_prefix, req_id)
            return None
        found = await asyncio.to_thread(_find_ig_file, req_id)
        if not found:
            await asyncio.to_thread(_cleanup_ig_prefix, req_id)
        return found
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        await asyncio.to_thread(_cleanup_ig_prefix, req_id)
        raise
    except asyncio.CancelledError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        await asyncio.to_thread(_cleanup_ig_prefix, req_id)
        raise
    except Exception as e:
        logger.warning("Instagram download error: %s", e)
        await asyncio.to_thread(_cleanup_ig_prefix, req_id)
        return None


def download_instagram(url):
    import yt_dlp

    req_id = uuid.uuid4().hex

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/{req_id}_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "sleep_interval": 5,
        "max_sleep_interval": 15,
    }
    if os.path.isfile(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
    proxy = os.getenv("IG_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    except Exception as e:
        logger.warning("Error downloading with yt-dlp: %s", e)
        return None
