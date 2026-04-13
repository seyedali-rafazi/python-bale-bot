# services/instagram.py

import os
import yt_dlp
import os
from dotenv import load_dotenv

load_dotenv() 
PROXY = os.getenv("PROXY")

def download_instagram(url):
    ydl_opts = {
        'proxy': PROXY,
        'outtmpl': 'ig_video_%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return os.path.abspath(filename)
    except Exception as e:
        print(f"Error downloading Instagram Video: {e}")
        return None
