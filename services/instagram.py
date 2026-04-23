# services/instagram.py

import os
import re
import yt_dlp
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROXY = os.getenv("PROXY")
DOWNLOAD_DIR = "ig_downloads"

Path(DOWNLOAD_DIR).mkdir(exist_ok=True)


def extract_username(text: str):
    text = text.strip().strip("/").lstrip("@")

    if "instagram.com" in text:
        match = re.search(r"instagram\.com/([^/?]+)", text)
        if match:
            return match.group(1)

    return text


def download_instagram_post(url: str):
    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "format": "best",
    }

    if PROXY:
        ydl_opts["proxy"] = PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if "entries" in info:
                info = info["entries"][0]

            file_path = ydl.prepare_filename(info)

            return {
                "success": True,
                "file": file_path,
                "caption": info.get("description", ""),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


def download_latest_post(username_or_url: str):
    username = extract_username(username_or_url)

    profile_url = f"https://www.instagram.com/{username}/"

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "playlistend": 1,
        "format": "best",
    }

    if PROXY:
        ydl_opts["proxy"] = PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(profile_url, download=True)

            if "entries" in info:
                info = info["entries"][0]

            file_path = ydl.prepare_filename(info)

            return {
                "success": True,
                "file": file_path,
                "caption": info.get("description", ""),
                "url": info.get("webpage_url"),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
