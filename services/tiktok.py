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
    """دانلود ویدیوی تیک‌تاک"""
    print(f"[TikTok] Start downloading: {url}")

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
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"[TikTok] Download failed: {stderr.decode()}")
        return None

    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
    return files[0] if files else None


async def search_tiktok_videos(query: str, max_results: int = 10):
    """جستجوی ویدیو در تیک‌تاک"""
    url = f"https://www.tikwm.com/api/feed/search?keywords={query}&count={max_results}"

    results = []

    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(1)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        return results

                    text_data = await response.text()

                    try:
                        data = json.loads(text_data)
                    except json.JSONDecodeError:
                        print("[TikTok] JSON decode error")
                        return results

                    if not isinstance(data, dict):
                        return results

                    if data.get("code") != 0:
                        return results

                    data_block = data.get("data")

                    if not isinstance(data_block, dict):
                        return results

                    videos = data_block.get("videos")

                    if not isinstance(videos, list):
                        return results

                    for item in videos:
                        if not isinstance(item, dict):
                            continue

                        title = item.get("title") or "بدون کپشن"
                        title = title.strip()
                        if not title:
                            title = "بدون کپشن"

                        if len(title) > 50:
                            title = title[:50] + "..."

                        video_id = item.get("video_id") or item.get("id")
                        if not video_id:
                            continue

                        author_data = item.get("author")

                        if isinstance(author_data, dict):
                            author = (
                                author_data.get("unique_id")
                                or author_data.get("id")
                                or "user"
                            )
                        elif isinstance(author_data, str):
                            author = author_data
                        else:
                            author = "user"

                        link = f"https://www.tiktok.com/@{author}/video/{video_id}"

                        results.append({"title": title, "url": link})

                        if len(results) >= max_results:
                            break

        except Exception as e:
            print(f"[TikTok] Search API Error: {e}")

    return results


async def get_tiktok_trends(count: int = 10):
    """گرفتن ویدیوهای ترند"""
    url = f"https://www.tikwm.com/api/feed/list?count={count}"

    results = []

    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(1)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        return results

                    data = await response.json()

                    if not isinstance(data, dict):
                        return results

                    data_block = data.get("data")

                    if not isinstance(data_block, list):
                        return results

                    for item in data_block:
                        if not isinstance(item, dict):
                            continue

                        title = item.get("title") or "Trending video"
                        video_id = item.get("video_id")

                        author_data = item.get("author")
                        if isinstance(author_data, dict):
                            author = author_data.get("unique_id", "user")
                        else:
                            author = "user"

                        if not video_id:
                            continue

                        link = f"https://www.tiktok.com/@{author}/video/{video_id}"

                        results.append({"title": title, "url": link})

                        if len(results) >= count:
                            break

        except Exception as e:
            print(f"[TikTok] Trends API Error: {e}")

    return results
