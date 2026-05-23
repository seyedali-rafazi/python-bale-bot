# services/music_identify.py

import os
import subprocess
from typing import Optional, Tuple

import aiohttp

from services.http_client import get_http_session

IDENTIFY_DIR = os.path.join("downloads", "music_identify")
MAX_DURATION_SEC = 180  # 3 minutes

os.makedirs(IDENTIFY_DIR, exist_ok=True)


def get_message_media(message) -> Optional[Tuple[object, str, Optional[int]]]:
    """Return (file_obj, filename, duration_sec) for voice/audio/video."""
    if message.voice:
        return message.voice, "voice.ogg", message.voice.duration
    if message.audio:
        name = message.audio.file_name or "audio.mp3"
        return message.audio, name, message.audio.duration
    if message.video:
        return message.video, "video.mp4", message.video.duration
    if message.video_note:
        return message.video_note, "video_note.mp4", message.video_note.duration
    if message.document and message.document.mime_type:
        mime = message.document.mime_type.lower()
        if mime.startswith("audio/") or mime.startswith("video/"):
            name = message.document.file_name or "media.bin"
            return message.document, name, None
    return None


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
