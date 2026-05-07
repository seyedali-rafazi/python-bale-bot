# services/instagram.py

import os
import instaloader
import asyncio
import yt_dlp
import uuid
from dotenv import load_dotenv
from services.warp_manager import rotate_warp_registration

load_dotenv()
DOWNLOAD_DIR = "ig_downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

_INSTALOADER_INSTANCE = None


def get_proxy():
    return os.getenv("PROXY")


def reset_instaloader_instance():
    global _INSTALOADER_INSTANCE
    _INSTALOADER_INSTANCE = None


def get_instaloader_instance():
    global _INSTALOADER_INSTANCE
    if _INSTALOADER_INSTANCE is not None:
        return _INSTALOADER_INSTANCE

    L = instaloader.Instaloader(
        download_pictures=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )
    username = os.getenv("IG_USERNAME", "danny75479")

    proxy = get_proxy()
    if proxy:
        proxies = {"http": proxy, "https": proxy}
        L.context._session.proxies = proxies
        print("✅ پروکسی برای instaloader تنظیم شد.")

    try:
        L.load_session_from_file(username, filename=f"session_{username}")
        print("✅ لاگین instaloader انجام شد.")
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


def should_rotate_proxy(error_text: str) -> bool:
    error_text = (error_text or "").lower()

    keywords = [
        "proxy",
        "connection",
        "timeout",
        "timed out",
        "429",
        "too many requests",
        "rate limit",
        "forbidden",
        "bad gateway",
        "checkpoint",
        "login required",
        "temporary block",
        "connection refused",
        "remote end closed connection",
        "network is unreachable",
        "failed to establish a new connection",
    ]

    return any(k in error_text for k in keywords)


def get_latest_post_sync(page_input, retry_count=2):
    username = extract_username(page_input)
    req_id = uuid.uuid4().hex
    target_dir = os.path.join(DOWNLOAD_DIR, f"req_{req_id}")

    try:
        os.makedirs(target_dir, exist_ok=True)
        L = get_instaloader_instance()

        profile = instaloader.Profile.from_username(L.context, username)
        post = next(profile.get_posts())
        L.download_post(post, target=target_dir)

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
        err = str(e)
        print(f"Error downloading post: {err}")

        if retry_count > 0 and should_rotate_proxy(err):
            print("⚠️ پروکسی/WARP مشکل دارد. در حال ساخت registration جدید...")
            ok = rotate_warp_registration()
            if ok:
                reset_instaloader_instance()
                print("✅ WARP جدید ساخته شد. تلاش مجدد...")
                return get_latest_post_sync(page_input, retry_count=retry_count - 1)

        return None, target_dir


async def get_latest_post(page_input):
    return await asyncio.to_thread(get_latest_post_sync, page_input)


def download_instagram(url, retry_count=2):
    req_id = uuid.uuid4().hex
    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/{req_id}_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }

    proxy = get_proxy()
    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    except Exception as e:
        err = str(e)
        print(f"Error downloading with yt-dlp: {err}")

        if retry_count > 0 and should_rotate_proxy(err):
            print("⚠️ پروکسی/WARP مشکل دارد. در حال rotate...")
            ok = rotate_warp_registration()
            if ok:
                print("✅ WARP جدید ساخته شد. تلاش مجدد yt-dlp...")
                return download_instagram(url, retry_count=retry_count - 1)

        return None
