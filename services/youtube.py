# services/youtube.py

import os
import yt_dlp
import os
from dotenv import load_dotenv

load_dotenv() 
PROXY = os.getenv("PROXY")

def download_youtube_video(url):
    ydl_opts = {
        'proxy': PROXY,
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'yt_video_%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
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
        'proxy': PROXY,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': '%(uploader)s - %(title)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')
            performer = info.get('uploader', 'Unknown Artist')
            expected_filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(expected_filename)
            final_filename = f"{base}.mp3"
            return os.path.abspath(final_filename), title, performer
    except Exception as e:
        print(f"Error downloading YT Audio: {e}")
        return None, None, None
