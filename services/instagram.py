# services/instagram.py

import os
import instaloader
import asyncio
import yt_dlp
import uuid
from dotenv import load_dotenv

TREND_HASHTAGS = ("reels", "viral", "trending", "explorepage")

load_dotenv()
DOWNLOAD_DIR = "ig_downloads"
COOKIES_FILE = "insta_cookies.txt"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

_INSTALOADER_INSTANCE = None


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
    session_file = f"session_{username}"

    try:
        L.load_session_from_file(username, filename=session_file)
    except Exception as e:
        print(f"❌ خطای بارگذاری session Instaloader: {e}")

    if not L.context.is_logged_in:
        password = os.getenv("IG_PASSWORD")
        if username and password:
            try:
                L.login(username, password)
                L.save_session_to_file(session_file)
                print("✅ لاگین instaloader با رمز عبور انجام شد.")
            except Exception as e:
                print(f"❌ خطای لاگین Instaloader: {e}")
        else:
            print(
                "⚠️ Instaloader لاگین نیست. IG_PASSWORD را در .env تنظیم کنید "
                "یا session را با instaloader --login به‌روز کنید."
            )
    else:
        print("✅ لاگین instaloader انجام شد.")

    _INSTALOADER_INSTANCE = L
    return L


def _ydl_list_opts(max_results: int | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
    }
    if os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    if max_results:
        opts["playlistend"] = max_results
    proxy = os.getenv("IG_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        opts["proxy"] = proxy
    return opts


def _entries_to_results(entries, max_results: int) -> list:
    results = []
    for entry in entries or []:
        if not entry:
            continue
        url = entry.get("url") or entry.get("webpage_url")
        if not url or "instagram.com" not in url:
            continue

        title = (
            entry.get("title")
            or entry.get("description")
            or entry.get("alt_title")
            or "بدون کپشن"
        )
        title = str(title).strip() or "بدون کپشن"
        if len(title) > 50:
            title = title[:50] + "..."

        results.append({"title": title, "url": url})
        if len(results) >= max_results:
            break
    return results


def _fetch_tag_posts_via_ytdlp(tag: str, max_results: int) -> list:
    tag = tag.lstrip("#").strip()
    if not tag:
        return []

    if not os.path.isfile(COOKIES_FILE):
        print(
            f"[Instagram] فایل کوکی {COOKIES_FILE} یافت نشد. "
            "جستجو/ترند به کوکی نیاز دارند."
        )
        return []

    url = f"https://www.instagram.com/explore/tags/{tag}/"
    try:
        with yt_dlp.YoutubeDL(_ydl_list_opts(max_results)) as ydl:
            info = ydl.extract_info(url, download=False)
        return _entries_to_results(info.get("entries"), max_results)
    except Exception as e:
        print(f"[Instagram] yt-dlp tag '{tag}' error: {e}")
        return []


def extract_username(text):
    text = text.strip().strip("/")
    if "instagram.com/" in text:
        parts = text.split("instagram.com/")
        username_part = parts[1].split("?")[0].split("/")[0]
        return username_part
    return text


def get_latest_post_sync(page_input):
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
        print(f"Error downloading post: {e}")
        return None, target_dir


async def get_latest_post(page_input):
    return await asyncio.to_thread(get_latest_post_sync, page_input)


def _post_to_result(post) -> dict | None:
    shortcode = getattr(post, "shortcode", None)
    if not shortcode:
        return None

    if post.is_video:
        url = f"https://www.instagram.com/reel/{shortcode}/"
    else:
        url = f"https://www.instagram.com/p/{shortcode}/"

    title = (post.caption or "بدون کپشن").strip()
    if not title:
        title = "بدون کپشن"
    if len(title) > 50:
        title = title[:50] + "..."

    return {"title": title, "url": url}


def search_instagram_posts_sync(query: str, max_results: int = 10):
    results = _fetch_tag_posts_via_ytdlp(query, max_results)
    if results:
        return results

    # Fallback only when Instaloader session is fully logged in
    hashtag_name = query.lstrip("#").strip()
    if not hashtag_name:
        return []

    try:
        L = get_instaloader_instance()
        if not L.context.is_logged_in:
            return []

        hashtag = instaloader.Hashtag.from_name(L.context, hashtag_name)
        for post in hashtag.get_posts():
            item = _post_to_result(post)
            if item:
                results.append(item)
            if len(results) >= max_results:
                break
    except Exception as e:
        print(f"[Instagram] Search fallback (instaloader) error: {e}")

    return results


def cookies_configured() -> bool:
    return os.path.isfile(COOKIES_FILE)


async def search_instagram_posts(query: str, max_results: int = 10):
    return await asyncio.to_thread(search_instagram_posts_sync, query, max_results)


def get_instagram_trends_sync(count: int = 10):
    results = []
    seen_urls = set()

    for tag in TREND_HASHTAGS:
        if len(results) >= count:
            break
        for item in _fetch_tag_posts_via_ytdlp(tag, count):
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            results.append(item)
            if len(results) >= count:
                return results

    if results or not os.path.isfile(COOKIES_FILE):
        return results

    try:
        L = get_instaloader_instance()
        if not L.context.is_logged_in:
            return results

        for post in L.get_explore_posts():
            item = _post_to_result(post)
            if not item or item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            results.append(item)
            if len(results) >= count:
                break
    except Exception as e:
        print(f"[Instagram] Explore trends fallback error: {e}")

    return results


async def get_instagram_trends(count: int = 10):
    return await asyncio.to_thread(get_instagram_trends_sync, count)


def download_instagram(url):
    req_id = uuid.uuid4().hex

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/{req_id}_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "sleep_interval": 5,
        "max_sleep_interval": 15,
    }
    if os.path.isfile(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
    proxy = os.getenv("IG_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    except Exception as e:
        print(f"Error downloading with yt-dlp: {e}")
        return None
