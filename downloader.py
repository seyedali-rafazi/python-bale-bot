# downloader.py

import os
import yt_dlp
from config import PROXY

# ==========================================
# 1. دانلود ویدیو از یوتیوب
# ==========================================
def download_youtube_video(url):
    """دانلود بهترین کیفیت یکپارچه ویدیو یوتیوب"""
    ydl_opts = {
        'proxy': PROXY,
        # دانلود بهترین کیفیتی که صدا و تصویرش به هم چسبیده و فرمت mp4 دارد
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'yt_video_%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # تبدیل مسیر به آدرس دقیق (مطلق) تا کتابخانه روبیکا ارور مسیر ندهد
            return os.path.abspath(filename)
    except Exception as e:
        print(f"Error downloading YT Video: {e}")
        return None

# ==========================================
# 2. دانلود فایل صوتی (MP3) از یوتیوب
# ==========================================
def download_youtube_audio(url):
    """دانلود صدا از یوتیوب و تبدیل به MP3"""
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

# ==========================================
# 3. دانلود از اینستاگرام
# ==========================================
def download_instagram(url):
    """دانلود پست یا ریلز از اینستاگرام"""
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
