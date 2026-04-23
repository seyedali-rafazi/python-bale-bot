# services/instagram.py

import os
import re
import yt_dlp
from pathlib import Path
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PrivateError

load_dotenv()

PROXY = os.getenv("PROXY")
DOWNLOAD_DIR = "ig_downloads"
IG_USERNAME = os.getenv("IG_USERNAME")  # اختیاری
IG_PASSWORD = os.getenv("IG_PASSWORD")  # اختیاری

Path(DOWNLOAD_DIR).mkdir(exist_ok=True)

cl = None


def get_client():
    """ساخت کلاینت اینستاگرام با لاگین (اختیاری)"""
    global cl
    if cl:
        return cl

    cl = Client()

    if PROXY:
        cl.set_proxy(PROXY)

    # اگر username/password داری، لاگین کن
    if IG_USERNAME and IG_PASSWORD:
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
        except:
            pass  # بدون لاگین ادامه بده

    return cl


def extract_username(text):
    text = text.strip().strip("/").lstrip("@")

    if "instagram.com/" in text:
        match = re.search(r"instagram\.com/([^/?]+)", text)
        return match.group(1) if match else None

    return text


def download_instagram_post(url):
    """دانلود با لینک مستقیم (yt-dlp)"""
    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "format": "best",
    }

    if PROXY:
        ydl_opts["proxy"] = PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            return {
                "success": True,
                "file": filename,
                "caption": info.get("description", "")[:200],
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_latest_post(username):
    """دانلود آخرین پست با instagrapi"""
    username = extract_username(username)

    try:
        client = get_client()

        user_id = client.user_id_from_username(username)
        medias = client.user_medias(user_id, amount=1)

        if not medias:
            return {"success": False, "error": "پستی پیدا نشد"}

        media = medias[0]

        # دانلود بر اساس نوع
        if media.media_type == 1:  # عکس
            file_path = client.photo_download(media.pk, folder=DOWNLOAD_DIR)
        elif media.media_type == 2:  # ویدیو
            file_path = client.video_download(media.pk, folder=DOWNLOAD_DIR)
        else:
            file_path = client.photo_download(media.pk, folder=DOWNLOAD_DIR)

        return {
            "success": True,
            "file": str(file_path),
            "caption": media.caption_text[:200] if media.caption_text else "",
            "post_url": f"https://www.instagram.com/p/{media.code}/",
        }

    except PrivateError:
        return {"success": False, "error": "اکانت پرایوت است"}
    except LoginRequired:
        return {"success": False, "error": "نیاز به لاگین (اکانت IG در .env تنظیم کن)"}
    except Exception as e:
        return {"success": False, "error": f"خطا: {str(e)}"}
