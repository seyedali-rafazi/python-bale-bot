# services/youtube.py

import os
import glob
import subprocess
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_TG_VIDEO_SIZE = 50 * 1024 * 1024


def compress_video(input_file, target_height=480):
    """فشرده‌سازی ویدیو با ffmpeg به صورت جداگانه"""
    output_file = input_file.rsplit(".", 1)[0] + "_compressed.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-vf", f"scale=-2:{target_height}",
        "-c:v", "libx264",
        "-crf", "30",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        output_file
    ]
    
    print(f"🔧 Compressing: {input_file}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0 and os.path.exists(output_file):
        new_size = os.path.getsize(output_file)
        print(f"✅ Compressed: {new_size / (1024*1024):.2f} MB")
        return output_file
    else:
        print(f"❌ ffmpeg error: {result.stderr[-500:]}")
        return None


def download_youtube_video(url):
    """دانلود ویدیو - بدون هیچ postprocessor"""
    
    ydl_opts = {
        "proxy": PROXY,
        # فقط فرمت‌های از پیش merge شده (نه جداگانه ویدیو+صدا)
        "format": "best[height<=480]/best[height<=720]/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": False,
        "no_warnings": False,
        # هیچ postprocessor نداریم
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🔍 Extracting info from: {url}")
            info = ydl.extract_info(url, download=True)
            
            video_id = info.get("id", "unknown")
            print(f"📹 Video ID: {video_id}")
            
            # پیدا کردن فایل دانلود شده
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            print(f"🔎 Found files: {files}")
            
            if not files:
                # فال‌بک: جدیدترین فایل
                all_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
                if all_files:
                    files = [max(all_files, key=os.path.getctime)]
            
            if not files:
                print("❌ No file found!")
                return None
            
            raw_file = files[0]
            file_size = os.path.getsize(raw_file)
            print(f"📦 Raw file: {raw_file} ({file_size / (1024*1024):.2f} MB)")
            
            # اگه حجمش بیشتر از 50MB هست، فشرده کن
            if file_size > MAX_TG_VIDEO_SIZE:
                print(f"⚠️ Too large ({file_size / (1024*1024):.1f} MB), compressing...")
                compressed = compress_video(raw_file)
                
                if compressed:
                    comp_size = os.path.getsize(compressed)
                    # اگه هنوز بزرگه، بیشتر فشرده کن
                    if comp_size > MAX_TG_VIDEO_SIZE:
                        print(f"⚠️ Still too large ({comp_size / (1024*1024):.1f} MB), compressing harder...")
                        os.remove(compressed)
                        compressed = compress_video_harder(raw_file)
                    
                    if compressed and os.path.exists(compressed):
                        os.remove(raw_file)
                        return os.path.abspath(compressed)
                
                # اگه فشرده‌سازی فیل شد، همون فایل اصلی رو برگردون
                print("⚠️ Compression failed, returning raw file")
                return os.path.abspath(raw_file)
            
            return os.path.abspath(raw_file)
            
    except Exception as e:
        print(f"❌ Error downloading: {e}")
        import traceback
        traceback.print_exc()
        return None


def compress_video_harder(input_file):
    """فشرده‌سازی شدیدتر برای فایل‌های خیلی بزرگ"""
    output_file = input_file.rsplit(".", 1)[0] + "_small.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-vf", "scale=-2:360",  # 360p
        "-c:v", "libx264",
        "-crf", "34",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "64k",
        "-movflags", "+faststart",
        output_file
    ]
    
    print(f"🔧 Hard compressing...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0 and os.path.exists(output_file):
        new_size = os.path.getsize(output_file)
        print(f"✅ Hard compressed: {new_size / (1024*1024):.2f} MB")
        return output_file
    else:
        print(f"❌ Hard compression failed: {result.stderr[-500:]}")
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
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": False,
        "noplaylist": True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🔍 Extracting audio from: {url}")
            info = ydl.extract_info(url, download=True)
            
            title = info.get("title", "Unknown Title")
            performer = info.get("uploader", "Unknown Artist")
            video_id = info.get("id", "unknown")
            
            pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
            files = glob.glob(pattern)
            mp3_files = [f for f in files if f.endswith(".mp3")]
            
            print(f"🔎 Found: {files} | MP3: {mp3_files}")
            
            if mp3_files:
                return os.path.abspath(mp3_files[0]), title, performer
            
            all_mp3 = glob.glob(os.path.join(DOWNLOAD_DIR, "*.mp3"))
            if all_mp3:
                latest = max(all_mp3, key=os.path.getctime)
                return os.path.abspath(latest), title, performer
            
            return None, None, None
            
    except Exception as e:
        print(f"❌ Error downloading audio: {e}")
        return None, None, None


def search_yt_videos(query, max_results=5):
    ydl_opts = {
        "proxy": PROXY,
        "extract_flat": True,
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
