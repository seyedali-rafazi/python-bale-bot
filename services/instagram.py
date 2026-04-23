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
    L = instaloader.Instaloader()
    username = os.getenv("IG_USERNAME", "danny75479")

    try:
        # ربات تلاش می‌کند از فایل سشنی که ساختید استفاده کند
        L.load_session_from_file(username, filename=f"session_{username}")
        print("✅ لاگین از طریق فایل سشن با موفقیت انجام شد.")
    except FileNotFoundError:
        print("❌ فایل سشن پیدا نشد! لطفا فایل سشن را کنار ربات قرار دهید.")
    except Exception as e:
        print(f"❌ خطای لاگین: {e}")

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
