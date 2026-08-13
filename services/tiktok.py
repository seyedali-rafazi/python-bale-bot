# services/tiktok.py
import os
import uuid
import asyncio
import glob
import json
import logging
import urllib.parse
import html
import re
from dotenv import load_dotenv

from services.http_client import get_http_session
from services.flaresolverr import flaresolverr_request

load_dotenv()

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TIKWM_API_SEMAPHORE = asyncio.Semaphore(2)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tikwm.com/",
}


def _get_proxy() -> str | None:
    return (
        os.getenv("TIKTOK_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or os.getenv("PROXY")
    )


def _extract_json_data(text: str) -> dict | list | None:
    """Extract and parse JSON payload even if wrapped inside HTML <pre> tags by Chrome/FlareSolverr."""
    if not text:
        return None
    clean_text = text.strip()

    # 1. Direct JSON parse
    try:
        return json.loads(clean_text)
    except Exception:
        pass

    # 2. Extract from <pre>...</pre> tag (Chromium JSON viewer wrapper)
    match = re.search(r"<pre[^>]*>([\s\S]*?)</pre>", clean_text, re.IGNORECASE)
    if match:
        extracted = html.unescape(match.group(1).strip())
        try:
            return json.loads(extracted)
        except Exception:
            pass

    # 3. Regex fallback to find JSON object or array
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", clean_text)
    if match:
        extracted = html.unescape(match.group(1).strip())
        try:
            return json.loads(extracted)
        except Exception:
            pass

    return None


async def _exec_ytdlp_download(url: str, proxy: str | None = None) -> str | None:
    req_id = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
        "--no-playlist",
    ]

    if proxy:
        cmd.extend(["--proxy", proxy])

    cmd.append(url)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="ignore")
            logger.warning("[TikTok] yt-dlp failed (proxy=%s): %s", proxy or "none", err_msg.strip()[:300])
            return None

        files = glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
        return files[0] if files else None

    except Exception as e:
        logger.exception("[TikTok] Exception running yt-dlp (proxy=%s): %s", proxy or "none", e)
        return None


async def download_tiktok_video(url: str):
    """دانلود ویدیوی تیک‌تاک با استفاده از yt-dlp (با فال‌بک دانلود مستقیم در صورت خرابی یا قطعی پروکسی)"""
    logger.info("[TikTok] Start downloading: %s", url)

    proxy = _get_proxy()

    # تلاش اول: با پروکسی در صورت وجود
    if proxy:
        file_path = await _exec_ytdlp_download(url, proxy=proxy)
        if file_path:
            return file_path
        logger.warning("[TikTok] Download with proxy '%s' failed. Retrying direct download without proxy...", proxy)

    # تلاش دوم / مستقیم: بدون پروکسی
    file_path = await _exec_ytdlp_download(url, proxy=None)
    if file_path:
        return file_path

    return None


async def search_tiktok_videos(query: str, max_results: int = 10):
    """
    جستجوی ویدیو در تیک‌تاک با انکودینگ کامل، تست مستقیم POST/GET
    و بای‌پاس کلادفلر (Cloudflare 403) با استفاده از FlareSolverr.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    results = []

    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(0.5)

        session = await get_http_session()

        endpoints = [
            "https://www.tikwm.com/api/feed/search",
            "https://tikwm.com/api/feed/search",
        ]

        proxy = _get_proxy()
        kwargs = {"headers": DEFAULT_HEADERS, "timeout": 15}
        if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
            kwargs["proxy"] = proxy

        cf_blocked = False

        for endpoint in endpoints:
            # روش ۱: ارسال POST مستقیم با فرم دیتا
            try:
                post_data = {
                    "keywords": clean_query,
                    "count": str(max_results),
                    "cursor": "0",
                    "web": "1",
                }
                async with session.post(endpoint, data=post_data, **kwargs) as response:
                    if response.status == 200:
                        text_data = await response.text()
                        data = _extract_json_data(text_data)
                        if data:
                            results = _parse_tikwm_search_response(data, max_results)
                            if results:
                                logger.info("[TikTok] POST search successful on %s for query '%s'", endpoint, clean_query)
                                return results
                    elif response.status == 403:
                        cf_blocked = True
                        logger.warning("[TikTok] POST search HTTP 403 (Cloudflare) from %s", endpoint)
                    else:
                        logger.warning("[TikTok] POST search HTTP %s from %s", response.status, endpoint)
            except Exception as e:
                logger.warning("[TikTok] POST search error on %s: %s", endpoint, e)

            # روش ۲: ارسال GET مستقیم با URL Query کاملاً انکود شده
            try:
                encoded_query = urllib.parse.quote(clean_query)
                get_url = f"{endpoint}?keywords={encoded_query}&count={max_results}&cursor=0&web=1"

                async with session.get(get_url, **kwargs) as response:
                    if response.status == 200:
                        text_data = await response.text()
                        data = _extract_json_data(text_data)
                        if data:
                            results = _parse_tikwm_search_response(data, max_results)
                            if results:
                                logger.info("[TikTok] GET search successful on %s for query '%s'", endpoint, clean_query)
                                return results
                    elif response.status == 403:
                        cf_blocked = True
                        logger.warning("[TikTok] GET search HTTP 403 (Cloudflare) from %s", endpoint)
                    else:
                        logger.warning("[TikTok] GET search HTTP %s from %s", response.status, endpoint)
            except Exception as e:
                logger.warning("[TikTok] GET search error on %s: %s", endpoint, e)

        # روش ۳: استفاده از FlareSolverr برای حل چالش کلادفلر در صورت 403
        if cf_blocked or not results:
            logger.info("[TikTok] Attempting FlareSolverr bypass for Cloudflare 403 challenge on query '%s'...", clean_query)
            
            target_url = "https://www.tikwm.com/api/feed/search"
            post_payload = f"keywords={urllib.parse.quote(clean_query)}&count={max_results}&cursor=0&web=1"
            
            headers_fs = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            
            # اول درخواست POST به FlareSolverr
            solution = await flaresolverr_request(
                url=target_url,
                method="POST",
                post_data=post_payload,
                headers=headers_fs,
                timeout=45,
            )
            
            # اگر POST پاسخ نداد، GET را هم امتحان میکنیم
            if not solution:
                encoded_query = urllib.parse.quote(clean_query)
                target_get_url = f"{target_url}?keywords={encoded_query}&count={max_results}&cursor=0&web=1"
                solution = await flaresolverr_request(
                    url=target_get_url,
                    method="GET",
                    timeout=45,
                )

            if solution and solution.get("response"):
                raw_resp = solution["response"]
                data = _extract_json_data(raw_resp)
                if data:
                    results = _parse_tikwm_search_response(data, max_results)
                    if results:
                        logger.info("[TikTok] FlareSolverr successfully retrieved %s search results for '%s'", len(results), clean_query)
                        return results
                else:
                    logger.error("[TikTok] FlareSolverr response could not be parsed as JSON: %s", raw_resp[:300])

        if not results:
            logger.error(
                "[TikTok] Search failed for query '%s': Direct requests got Cloudflare 403 and FlareSolverr did not return results. "
                "Ensure FlareSolverr docker container is running (docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr).",
                clean_query,
            )

    return results


def _parse_tikwm_search_response(data: dict, max_results: int) -> list:
    results = []
    if not isinstance(data, dict):
        logger.warning("[TikTok] Search response is not a dict: %s", type(data))
        return results

    code = data.get("code")
    if code != 0:
        msg = data.get("msg") or data.get("message") or "Unknown API error"
        logger.warning("[TikTok] Search API returned code %s: %s", code, msg)
        return results

    data_block = data.get("data")
    videos = []

    if isinstance(data_block, dict):
        videos = data_block.get("videos") or data_block.get("list") or []
    elif isinstance(data_block, list):
        videos = data_block

    if not isinstance(videos, list):
        return results

    for item in videos:
        if not isinstance(item, dict):
            continue

        title = item.get("title") or item.get("desc") or "بدون کپشن"
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

    return results


async def get_tiktok_trends(count: int = 10):
    """گرفتن ویدیوهای ترند تیک‌تاک با پشتیبانی بای‌پاس کلادفلر FlareSolverr"""
    results = []

    async with TIKWM_API_SEMAPHORE:
        await asyncio.sleep(0.5)

        session = await get_http_session()

        endpoints = [
            f"https://www.tikwm.com/api/feed/list?region=US&count={count}",
            f"https://tikwm.com/api/feed/list?region=US&count={count}",
        ]

        proxy = _get_proxy()
        kwargs = {"headers": DEFAULT_HEADERS, "timeout": 15}
        if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
            kwargs["proxy"] = proxy

        cf_blocked = False

        for url in endpoints:
            try:
                async with session.get(url, **kwargs) as response:
                    if response.status == 200:
                        text_data = await response.text()
                        data = _extract_json_data(text_data)
                        if isinstance(data, dict) and data.get("code") == 0:
                            data_block = data.get("data")
                            videos = []
                            if isinstance(data_block, list):
                                videos = data_block
                            elif isinstance(data_block, dict):
                                videos = data_block.get("videos") or data_block.get("list") or []

                            for item in videos:
                                if not isinstance(item, dict):
                                    continue

                                title = item.get("title") or item.get("desc") or "Trending video"
                                video_id = item.get("video_id") or item.get("id")

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

                            if results:
                                return results
                    elif response.status == 403:
                        cf_blocked = True
                        logger.warning("[TikTok] Trends HTTP 403 (Cloudflare) from %s", url)

            except Exception as e:
                logger.warning("[TikTok] Trends API Error for %s: %s", url, e)

        # تلاش با FlareSolverr در صورت کلادفلر
        if cf_blocked or not results:
            target_url = f"https://www.tikwm.com/api/feed/list?region=US&count={count}"
            solution = await flaresolverr_request(url=target_url, method="GET", timeout=45)

            if solution and solution.get("response"):
                raw_resp = solution["response"]
                data = _extract_json_data(raw_resp)
                if isinstance(data, dict) and data.get("code") == 0:
                    data_block = data.get("data")
                    videos = []
                    if isinstance(data_block, list):
                        videos = data_block
                    elif isinstance(data_block, dict):
                        videos = data_block.get("videos") or data_block.get("list") or []

                    for item in videos:
                        if not isinstance(item, dict):
                            continue

                        title = item.get("title") or item.get("desc") or "Trending video"
                        video_id = item.get("video_id") or item.get("id")

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

                    if results:
                        return results

    return results
