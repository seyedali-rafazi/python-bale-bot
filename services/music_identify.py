# services/music_identify.py

import os
import subprocess
from typing import Optional, Tuple

import aiohttp

from services.http_client import get_http_session

IDENTIFY_DIR = os.path.join("downloads", "music_identify")
MAX_DURATION_SEC = 180  # 3 minutes

os.makedirs(IDENTIFY_DIR, exist_ok=True)


def get_message_media(message) -> Optional[Tuple[object, str]]:
    """Return (file_obj, filename) for voice/audio/video."""
    if message.voice:
        return message.voice, "voice.ogg"
    if message.audio:
        name = message.audio.file_name or "audio.mp3"
        return message.audio, name
    if message.video:
        return message.video, "video.mp4"
    if message.video_note:
        return message.video_note, "video_note.mp4"
    if message.document and message.document.mime_type:
        mime = message.document.mime_type.lower()
        if mime.startswith("audio/") or mime.startswith("video/"):
            name = message.document.file_name or "media.bin"
            return message.document, name
    return None


def _parse_api_duration(duration: Optional[int], file_size: Optional[int]) -> Optional[int]:
    """
    Normalize duration from messenger API.
    Bale may put file_size (bytes) in the duration field instead of seconds.
    """
    if duration is None or duration <= 0:
        return None
    if file_size and duration == file_size:
        return None
    # Obvious byte-as-seconds: ~20KB voice reported as 19854 "seconds"
    if file_size and duration > MAX_DURATION_SEC and file_size < duration:
        return None
    # Milliseconds (e.g. 19000 ms for 19 s)
    if duration > MAX_DURATION_SEC and duration <= MAX_DURATION_SEC * 1000:
        as_sec = duration / 1000.0
        if as_sec <= MAX_DURATION_SEC + 5:
            return int(round(as_sec))
    if duration <= MAX_DURATION_SEC:
        return duration
    return duration


def get_api_duration_sec(file_obj) -> Optional[int]:
    duration = getattr(file_obj, "duration", None)
    file_size = getattr(file_obj, "file_size", None)
    return _parse_api_duration(duration, file_size)


def probe_media_duration_sec(file_path: str) -> Optional[float]:
    """Read real duration from file via ffprobe."""
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
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = float(result.stdout.strip())
        return value if value > 0 else None
    except Exception as e:
        print(f"ffprobe duration error: {e}")
        return None


def format_duration_fa(seconds: float) -> str:
    total = int(round(seconds))
    if total < 60:
        return f"{total} ثانیه"
    return f"{total // 60} دقیقه و {total % 60} ثانیه"


def extract_audio_to_mp3(input_path: str, output_path: str, max_seconds: int = MAX_DURATION_SEC) -> bool:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-t",
        str(max_seconds),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "4",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"ffmpeg extract audio error: {e}")
        return False


def _parse_shazam_result(data: dict) -> Optional[dict]:
    track = (data or {}).get("track")
    if not track:
        return None
    title = track.get("title")
    if not title:
        return None
    return {
        "title": title,
        "artist": track.get("subtitle") or "ناشناس",
    }


async def _recognize_with_shazam(file_path: str) -> Optional[dict]:
    try:
        from shazamio import Shazam
        from shazamio_core import SearchParams
    except ImportError:
        return None

    try:
        shazam = Shazam()
        out = await shazam.recognize(
            file_path,
            options=SearchParams(segment_duration_seconds=12),
        )
        return _parse_shazam_result(out)
    except Exception as e:
        print(f"Shazam recognize error: {e}")
        return None


async def _recognize_with_audd(file_path: str) -> Optional[dict]:
    token = os.getenv("AUDD_API_TOKEN", "").strip()
    if not token:
        return None

    try:
        with open(file_path, "rb") as audio_file:
            file_bytes = audio_file.read()

        session = await get_http_session()
        form = aiohttp.FormData()
        form.add_field("api_token", token)
        form.add_field("return", "apple_music,spotify")
        form.add_field(
            "file",
            file_bytes,
            filename=os.path.basename(file_path),
            content_type="audio/mpeg",
        )
        async with session.post("https://api.audd.io/", data=form) as resp:
            data = await resp.json()

        if data.get("status") != "success" or not data.get("result"):
            return None
        result = data["result"]
        title = result.get("title")
        if not title:
            return None
        return {
            "title": title,
            "artist": result.get("artist") or "ناشناس",
        }
    except Exception as e:
        print(f"AudD recognize error: {e}")
        return None


async def recognize_music_from_file(file_path: str) -> Optional[dict]:
    """Identify song from an audio file. Returns {title, artist} or None."""
    result = await _recognize_with_shazam(file_path)
    if result:
        return result
    return await _recognize_with_audd(file_path)
