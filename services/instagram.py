# services/instagram.py

import os
import instaloader
import asyncio
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")
DOWNLOAD_DIR = "ig_downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


def get_instaloader_instance():
    L = instaloader.Instaloader(
        dirname_pattern=DOWNLOAD_DIR,
        download_pictures=True,
        download_video_thumbnails=False,
        download_videos=True,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )

    # تنظیم پروکسی
    if PROXY:
        L.context._session.proxies = {"http": PROXY, "https": PROXY}

    # خواندن اطلاعات از فایل .env و لاگین کردن
    ig_username = os.getenv("IG_USERNAME")
    ig_password = os.getenv("IG_PASSWORD")

    if ig_username and ig_password:
        try:
            L.login(ig_username, ig_password)
        except Exception as e:
            print(f"Instaloader Login Error: {e}")

    return L


def extract_username(text):
    text = text.strip().strip("/")
    if "instagram.com/" in text:
        parts = text.split("instagram.com/")
        username_part = parts[1].split("?")[0].split("/")[0]
        return username_part
    return text


def get_latest_post_sync(page_input):
    username = extract_username(page_input)
    L = get_instaloader_instance()

    try:
        profile = instaloader.Profile.from_username(L.context, username)
        post = next(profile.get_posts())  # گرفتن اولین (آخرین) پست
        L.download_post(post, target=DOWNLOAD_DIR)

        # پیدا کردن فایل دانلود شده (ویدیو یا عکس)
        downloaded_files = os.listdir(DOWNLOAD_DIR)
        media_files = [
            f
            for f in downloaded_files
            if f.endswith((".mp4", ".jpg")) and username in f
        ]

        if media_files:
            # مرتب‌سازی بر اساس زمان تغییر تا جدیدترین فایل برگردانده شود
            media_files.sort(
                key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
                reverse=True,
            )
            return os.path.join(DOWNLOAD_DIR, media_files[0])
        return None
    except Exception as e:
        print(f"Error downloading post: {e}")
        return None


# تابع کمکی برای فراخوانی ناهمگام (Async)
async def get_latest_post(page_input):
    return await asyncio.to_thread(get_latest_post_sync, page_input)


# اضافه شدن تابع دانلود با لینک مستقیم
def download_instagram(url):
    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }

    if PROXY:
        ydl_opts["proxy"] = PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        print(f"Error downloading with yt-dlp: {e}")
        return None
