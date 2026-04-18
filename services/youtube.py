# services/youtube.py

import os
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")


def download_youtube_video(url):
    ydl_opts = {
        "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": "%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return os.path.abspath(filename)
    except Exception as e:
        print(f"Error downloading YT Video: {e}")
        return None


def download_youtube_audio(url):
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
        "outtmpl": "%(uploader)s - %(title)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown Title")
            performer = info.get("uploader", "Unknown Artist")
            expected_filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(expected_filename)
            final_filename = f"{base}.mp3"
            return os.path.abspath(final_filename), title, performer
    except Exception as e:
        print(f"Error downloading YT Audio: {e}")
        return None, None, None


def search_yt_videos(query, max_results=5):
    ydl_opts = {
        "proxy": PROXY,
        "extract_flat": True,
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # اگر سرچ گلوبال بود، ytsearch استفاده میشود
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
