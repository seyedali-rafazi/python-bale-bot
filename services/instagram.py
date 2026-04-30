# services/instagram.py

import os
import instaloader
import asyncio
import yt_dlp
import uuid
from dotenv import load_dotenv

load_dotenv()
PROXY = os.getenv("PROXY")
DOWNLOAD_DIR = "ig_downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# نمونه یکتا (Singleton) برای جلوگیری از لاگین مجدد در هر درخواست
_INSTALOADER_INSTANCE = None


def get_instaloader_instance():
    global _INSTALOADER_INSTANCE
    if _INSTALOADER_INSTANCE is not None:
        return _INSTALOADER_INSTANCE

    # غیرفعال کردن دانلود فایل‌های اضافی برای افزایش سرعت
    L = instaloader.Instaloader(
        download_pictures=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )
    username = os.getenv("IG_USERNAME", "danny75479")

    if PROXY:
        proxies = {"http": PROXY, "https": PROXY}
        L.context._session.proxies = proxies
        print("✅ پروکسی برای instaloader تنظیم شد.")

    try:
        L.load_session_from_file(username, filename=f"session_{username}")
        print("✅ لاگین instaloader یک بار برای همیشه انجام شد.")
    except Exception as e:
        print(f"❌ خطای لاگین Instaloader: {e}")

    _INSTALOADER_INSTANCE = L
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

    # ساخت یک پوشه موقت با شناسه یکتا برای جلوگیری از تداخل درخواست‌های همزمان
    req_id = uuid.uuid4().hex
    target_dir = os.path.join(DOWNLOAD_DIR, f"req_{req_id}")

    try:
        profile = instaloader.Profile.from_username(L.context, username)
        post = next(profile.get_posts())
        L.download_post(post, target=target_dir)

        # پیدا کردن فایل مدیا در پوشه اختصاصی همین کاربر
        downloaded_files = os.listdir(target_dir)
        media_files = [f for f in downloaded_files if f.endswith((".mp4", ".jpg"))]

        if media_files:
            media_files.sort(
                key=lambda x: os.path.getmtime(os.path.join(target_dir, x)),
                reverse=True,
            )
            return os.path.join(target_dir, media_files[0]), target_dir

        return None, target_dir
    except Exception as e:
        print(f"Error downloading post: {e}")
        return None, target_dir


async def get_latest_post(page_input):
    return await asyncio.to_thread(get_latest_post_sync, page_input)


def download_instagram(url):
    req_id = uuid.uuid4().hex
    ydl_opts = {
        # استفاده از UUID در نام فایل برای جلوگیری از جایگزین شدن فایل کاربران دیگر
        "outtmpl": f"{DOWNLOAD_DIR}/{req_id}_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }

    if PROXY:
        ydl_opts["proxy"] = PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        print(f"Error downloading with yt-dlp: {e}")
        return None
