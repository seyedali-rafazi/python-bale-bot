# services/tiktok.py
import os
import uuid
import asyncio
import glob
import json
import aiohttp
from dotenv import load_dotenv

load_dotenv()
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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

    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(
            f"❌ [TikTok Service] Process Failed with return code {process.returncode}"
        )
        return None

    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
    if files:
        return files[0]
    else:
        return None


async def search_tiktok_videos(query: str, max_results: int = 10):
    """جستجوی غیرهمزمان در تیک‌تاک با aiohttp و API tikwm"""
    url = f"https://www.tikwm.com/api/feed/search?keywords={query}&count={max_results}"
    results = []

    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(1)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        text_data = await response.text()
                        try:
                            data = json.loads(text_data)
                            if (
                                isinstance(data, dict)
                                and data.get("code") == 0
                                and "data" in data
                            ):
                                for item in data.get("data", []):
                                    title = item.get("title", "بدون کپشن")
                                    if not title or title.strip() == "":
                                        title = "بدون کپشن"
                                    title = title[:50] + (
                                        "..." if len(title) > 50 else ""
                                    )

                                    video_id = item.get("video_id") or item.get("id")
                                    author = item.get("author", {}).get(
                                        "unique_id", "user"
                                    )
                                    link = f"https://www.tiktok.com/@{author}/video/{video_id}"

                                    results.append({"title": title, "url": link})

                                    if len(results) >= max_results:
                                        break
                            else:
                                print(
                                    f"API returned unexpected data: {text_data[:100]}"
                                )
                        except json.JSONDecodeError:
                            print(f"Failed to parse JSON. Response: {text_data[:100]}")
        except Exception as e:
            print(f"Search API Error: {e}")

    return results


async def get_tiktok_trends():
    """دریافت غیرهمزمان ترندهای تیک‌تاک با aiohttp"""
    url = "https://www.tikwm.com/api/feed/list?region=US&count=10"
    results = []

    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(1)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        text_data = await response.text()
                        try:
                            data = json.loads(text_data)
                            if isinstance(data, dict) and data.get("code") == 0:
                                for item in data.get("data", []):
                                    title = item.get("title", "بدون کپشن")[:50]
                                    video_id = item.get("video_id") or item.get("id")
                                    author = item.get("author", {}).get(
                                        "unique_id", "user"
                                    )
                                    link = f"https://www.tiktok.com/@{author}/video/{video_id}"
                                    results.append({"title": title, "url": link})
                        except json.JSONDecodeError:
                            print(f"Failed to parse JSON. Response: {text_data[:100]}")
        except Exception as e:
            print(f"Trend API Error: {e}")

    return results
