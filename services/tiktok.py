# services/tiktok.py
import os
import uuid
import asyncio
import glob
import aiohttp
from dotenv import load_dotenv

load_dotenv()
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# محدودیت: حداکثر ۲ درخواست همزمان به API سایت tikwm برای جلوگیری از بن شدن IP
TIKWM_API_SEMAPHORE = asyncio.Semaphore(2)


async def download_tiktok_video(url: str):
    """دانلود غیرهمزمان ویدیوی تیک‌تاک"""
    print(f"🎬 [TikTok Service] Start downloading: {url}")
    req_id = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        "bv*+ba/b",
        "-o",
        output_template,
        "--no-playlist",
        url,
    ]

    print(f"⚙️ [TikTok Service] Running command: {' '.join(cmd)}")

    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    # لاگ‌ها (بایت به رشته تبدیل می‌شوند)
    if stdout:
        print(f"📝 [TikTok Service] STDOUT:\n{stdout.decode().strip()}")
    if stderr:
        print(f"⚠️ [TikTok Service] STDERR:\n{stderr.decode().strip()}")

    if process.returncode != 0:
        print(
            f"❌ [TikTok Service] Process Failed with return code {process.returncode}"
        )
        return None

    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
    if files:
        print(f"✅ [TikTok Service] Download successful: {files[0]}")
        return files[0]
    else:
        print(f"❌ [TikTok Service] File not found for: tt_{req_id}.*")
        return None


async def search_tiktok_videos(query: str, max_results: int = 10):
    """جستجوی غیرهمزمان در تیک‌تاک با aiohttp و API tikwm"""
    url = f"https://www.tikwm.com/api/feed/search?keywords={query}&count={max_results}"
    results = []

    # اعمال محدودیت برای جلوگیری از بن شدن
    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(1)  # ۱ ثانیه تاخیر اجباری بین درخواست‌ها
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        # بررسی موفق بودن دریافت دیتا
                        if data.get("code") == 0 and "data" in data:
                            for item in data.get("data", []):
                                title = item.get("title", "بدون کپشن")
                                if not title or title.strip() == "":
                                    title = "بدون کپشن"
                                title = title[:50] + ("..." if len(title) > 50 else "")

                                video_id = item.get("video_id") or item.get("id")
                                author = item.get("author", {}).get("unique_id", "user")
                                link = (
                                    f"https://www.tiktok.com/@{author}/video/{video_id}"
                                )

                                results.append({"title": title, "url": link})

                                if len(results) >= max_results:
                                    break
        except Exception as e:
            print(f"Search API Error: {e}")

    return results


async def get_tiktok_trends():
    """دریافت غیرهمزمان ترندهای تیک‌تاک با aiohttp"""
    url = "https://www.tikwm.com/api/feed/list?region=US&count=10"
    results = []

    # اعمال محدودیت برای جلوگیری از بن شدن
    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(1)  # ۱ ثانیه تاخیر اجباری بین درخواست‌ها
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 0:
                            for item in data.get("data", []):
                                title = item.get("title", "بدون کپشن")[:50]
                                video_id = item.get("video_id") or item.get("id")
                                author = item.get("author", {}).get("unique_id", "user")
                                link = (
                                    f"https://www.tiktok.com/@{author}/video/{video_id}"
                                )
                                results.append({"title": title, "url": link})
        except Exception as e:
            print(f"Trend API Error: {e}")

    return results
