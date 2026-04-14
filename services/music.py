# ایجاد فایل جدید services/music.py

import os
import subprocess
import glob
import yt_dlp

def download_spotify_track(url, chat_id):
    try:
        download_dir = f"temp_spotify_{chat_id}"
        os.makedirs(download_dir, exist_ok=True)
        command = ["spotdl", url, "--output", download_dir]
        subprocess.run(command, capture_output=True, text=True)
        files = glob.glob(os.path.join(download_dir, "*.mp3"))
        if files:
            return files[0]
        return None
    except Exception as e:
        print(f"Spotify Error: {e}")
        return None

def search_and_download_music(query, chat_id):
    try:
        download_dir = f"temp_search_{chat_id}"
        os.makedirs(download_dir, exist_ok=True)
        file_path_template = os.path.join(download_dir, "%(title)s.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': file_path_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # جستجو و دانلود اولین نتیجه
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            entries = info.get('entries', [])
            if entries:
                downloaded_title = entries[0]['title']
                mp3_file = os.path.join(download_dir, f"{downloaded_title}.mp3")
                if os.path.exists(mp3_file):
                    return mp3_file, downloaded_title
        return None, None
    except Exception as e:
        print(f"Music Search Error: {e}")
        return None, None
