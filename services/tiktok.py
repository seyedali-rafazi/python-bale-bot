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
import threading
import time
import aiohttp
from dotenv import load_dotenv

from core.task_utils import remove_file_async, stream_aiohttp_to_file
from services.cache_service import cache_get, cache_set
from services.http_client import get_http_session
from services.flaresolverr import flaresolverr_request
from services.youtube import get_ytdlp_executable

load_dotenv()

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TIKWM_API_SEMAPHORE = asyncio.Semaphore(2)
_TIKTOK_YTDLP_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("TIKTOK_YTDLP_CONCURRENT", "3"))))
_AJAX_DOWNLOADER_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("TIKTOK_AJAX_CONCURRENT", "3"))))
_TIKTOK_MAX_BYTES = int(os.getenv("TIKTOK_MAX_BYTES", str(512 * 1024 * 1024)))
_tikwm_last_call = 0.0
_tikwm_rate_lock = asyncio.Lock()


async def _pace_tikwm_request(min_interval: float = 0.5) -> None:
    global _tikwm_last_call
    async with _tikwm_rate_lock:
        now = time.monotonic()
        wait = min_interval - (now - _tikwm_last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _tikwm_last_call = time.monotonic()

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


async def _download_stream_to_file(
    download_url: str,
    output_path: str,
    proxy: str | None = None,
    referer: str = "https://www.tikwm.com/",
) -> bool:
    """دانلود استریم فایل ویدیو از URL مستقیم روی دیسک با aiohttp"""
    session = await get_http_session()
    headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Referer": referer,
        "Accept": "*/*",
    }

    kwargs = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=60)}
    if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
        kwargs["proxy"] = proxy

    try:
        async with session.get(download_url, **kwargs) as resp:
            if resp.status != 200:
                logger.warning("[TikTok] Direct stream download returned HTTP %s for URL: %s", resp.status, download_url[:100])
                return False

            downloaded = await stream_aiohttp_to_file(
                resp, output_path, chunk_size=512 * 1024, max_bytes=_TIKTOK_MAX_BYTES
            )

        if downloaded > 1024:
            return True
        await remove_file_async(output_path)
        return False
    except Exception as e:
        logger.warning("[TikTok] Stream download exception: %s", e)
        await remove_file_async(output_path)
        return False


async def _fetch_tikwm_video_info(
    url: str,
    proxy: str | None = None,
    allow_solver: bool = True,
    solver_only: bool = False,
) -> dict | None:
    """دریافت متادیتا و لینک‌های مستقیم دانلود از TikWM API"""
    clean_url = url.strip()
    session = await get_http_session()

    endpoints = [
        "https://www.tikwm.com/api/",
        "https://tikwm.com/api/",
    ]

    kwargs = {"headers": DEFAULT_HEADERS, "timeout": aiohttp.ClientTimeout(total=20)}
    if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
        kwargs["proxy"] = proxy

    cf_blocked = False

    if not solver_only:
        async with TIKWM_API_SEMAPHORE:
            await _pace_tikwm_request()
            for endpoint in endpoints:
                # روش اول: درخواست POST
                try:
                    post_data = {"url": clean_url, "hd": "1"}
                    async with session.post(endpoint, data=post_data, **kwargs) as resp:
                        if resp.status == 200:
                            text_data = await resp.text()
                            data = _extract_json_data(text_data)
                            if isinstance(data, dict) and data.get("code") == 0 and data.get("data"):
                                return data.get("data")
                        elif resp.status == 403:
                            cf_blocked = True
                except Exception as e:
                    logger.warning("[TikTok] TikWM POST error on %s: %s", endpoint, e)

                # روش دوم: درخواست GET
                try:
                    encoded_url = urllib.parse.quote(clean_url)
                    get_url = f"{endpoint}?url={encoded_url}&hd=1"
                    async with session.get(get_url, **kwargs) as resp:
                        if resp.status == 200:
                            text_data = await resp.text()
                            data = _extract_json_data(text_data)
                            if isinstance(data, dict) and data.get("code") == 0 and data.get("data"):
                                return data.get("data")
                        elif resp.status == 403:
                            cf_blocked = True
                except Exception as e:
                    logger.warning("[TikTok] TikWM GET error on %s: %s", endpoint, e)

    # روش سوم: دور زدن کلادفلر با Byparr / FlareSolverr در صورت 403
    if (cf_blocked or solver_only) and allow_solver:
        logger.info("[TikTok] TikWM blocked by Cloudflare (403), attempting Byparr/FlareSolverr...")
        try:
            encoded_url = urllib.parse.quote(clean_url)
            solution = await flaresolverr_request(
                url=f"https://www.tikwm.com/api/?url={encoded_url}&hd=1",
                method="GET",
                timeout=60,
            )
            if not solution:
                solution = await flaresolverr_request(
                    url="https://www.tikwm.com/api/",
                    method="POST",
                    post_data=f"url={encoded_url}&hd=1",
                    timeout=60,
                )
            if solution and solution.get("response"):
                data = _extract_json_data(solution["response"])
                if isinstance(data, dict) and data.get("code") == 0 and data.get("data"):
                    return data.get("data")
        except Exception as e:
            logger.warning("[TikTok] Byparr/FlareSolverr error: %s", e)

    return None


def _parse_ajax_downloader_links(html_fragment: str) -> list[str]:
    """Extract MP4 download links from SaveTik/TikVid HTML fragment, prioritizing HD."""
    if not html_fragment:
        return []

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_fragment, "html.parser")
    hd_links: list[str] = []
    sd_links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        label = anchor.get_text(" ", strip=True).lower()
        if "mp4" not in label:
            continue
        if "hd" in label:
            hd_links.append(href)
        else:
            sd_links.append(href)

    # Deduplicate while preserving HD-first priority
    return list(dict.fromkeys(hd_links + sd_links))


_primp_clients: dict[str | None, tuple[object, threading.Lock]] = {}
_primp_lock = threading.Lock()


def _get_primp_client(primp_mod, proxy: str | None = None):
    valid_proxy = (
        proxy
        if proxy and (proxy.startswith("http://") or proxy.startswith("https://"))
        else None
    )
    with _primp_lock:
        entry = _primp_clients.get(valid_proxy)
        if entry is None:
            if len(_primp_clients) >= 16:
                _primp_clients.clear()
            client_kwargs = {"impersonate": "chrome_145"}
            if valid_proxy:
                client_kwargs["proxy"] = valid_proxy
            client = primp_mod.Client(**client_kwargs)
            entry = (client, threading.Lock())
            _primp_clients[valid_proxy] = entry
        return entry


async def _fetch_ajax_downloader_urls(url: str, proxy: str | None = None) -> list[tuple[str, str]]:
    """Query SaveTik and TikVid via primp TLS impersonation to extract direct MP4 URLs."""
    try:
        import primp
    except ImportError:
        logger.warning("[TikTok] primp is not installed; skipping SaveTik/TikVid fallback.")
        return []

    providers = [
        ("https://savetik.co/api/ajaxSearch", "https://savetik.co/"),
        ("https://tikvid.io/api/ajaxSearch", "https://tikvid.io/"),
    ]

    def _query_sync() -> list[tuple[str, str]]:
        client, client_lock = _get_primp_client(primp, proxy)

        collected: list[tuple[str, str]] = []
        with client_lock:
            for endpoint, referer in providers:
                try:
                    resp = client.post(endpoint, data={"q": url, "lang": "en"}, timeout=15)
                    if resp.status_code != 200:
                        logger.warning("[TikTok] %s returned HTTP %s", endpoint, resp.status_code)
                        continue
                    payload = resp.json()
                    html_fragment = payload.get("data") if isinstance(payload, dict) else None
                    if not html_fragment:
                        continue
                    for dl_url in _parse_ajax_downloader_links(html_fragment):
                        collected.append((dl_url, referer))
                    if collected:
                        return collected
                except Exception as exc:
                    logger.warning("[TikTok] %s error: %s", endpoint, exc)
        return collected

    async with _AJAX_DOWNLOADER_SEMAPHORE:
        return await asyncio.to_thread(_query_sync)


async def _exec_ytdlp_download(url: str, proxy: str | None = None) -> str | None:
    req_id = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.%(ext)s")

    cmd = get_ytdlp_executable() + [
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        str(_TIKTOK_MAX_BYTES),
        "-o",
        output_template,
        "--no-playlist",
        "--user-agent",
        DEFAULT_HEADERS["User-Agent"],
        "--no-check-certificates",
    ]

    cookie_file = os.getenv("YTDLP_COOKIE_FILE", "cookies.txt")
    if os.path.exists(cookie_file):
        cmd.extend(["--cookies", cookie_file])

    if proxy:
        cmd.extend(["--proxy", proxy])

    cmd.append(url)

    def _cleanup_tt_req():
        for p in glob.glob(os.path.join(DOWNLOAD_DIR, f"tt_{req_id}*")):
            try:
                os.remove(p)
            except OSError:
                pass

    try:
        async with _TIKTOK_YTDLP_SEMAPHORE:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180.0)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                await asyncio.to_thread(_cleanup_tt_req)
                logger.warning("[TikTok] yt-dlp timed out after 180s (proxy=%s)", proxy or "none")
                return None
            except asyncio.CancelledError:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                await asyncio.to_thread(_cleanup_tt_req)
                raise

            if process.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="ignore")
                logger.warning("[TikTok] yt-dlp failed (proxy=%s): %s", proxy or "none", err_msg.strip()[:300])
                await asyncio.to_thread(_cleanup_tt_req)
                return None

            files = [
                f
                for f in await asyncio.to_thread(glob.glob, os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.*"))
                if not f.endswith((".part", ".ytdl", ".temp"))
            ]
            return files[0] if files else None

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("[TikTok] Exception running yt-dlp (proxy=%s): %s", proxy or "none", e)
        await asyncio.to_thread(_cleanup_tt_req)
        return None


async def _try_tikwm_download(
    clean_url: str,
    output_path: str,
    proxy: str | None,
    allow_solver: bool,
    solver_only: bool = False,
) -> bool:
    """Attempt downloading a TikTok video via TikWM API (optionally via Byparr/FlareSolverr)."""
    video_data = await _fetch_tikwm_video_info(
        clean_url, proxy=proxy, allow_solver=allow_solver, solver_only=solver_only
    )
    if not video_data and proxy and not solver_only:
        video_data = await _fetch_tikwm_video_info(
            clean_url, proxy=None, allow_solver=allow_solver
        )

    if not video_data:
        return False

    video_url = (
        video_data.get("hdplay")
        or video_data.get("play")
        or video_data.get("wmplay")
    )
    if not video_url:
        return False

    if video_url.startswith("/"):
        video_url = f"https://www.tikwm.com{video_url}"

    logger.info("[TikTok] Direct video URL extracted from TikWM API, downloading file...")
    downloaded = await _download_stream_to_file(video_url, output_path, proxy=proxy)
    if not downloaded and proxy:
        downloaded = await _download_stream_to_file(video_url, output_path, proxy=None)

    return bool(downloaded and await asyncio.to_thread(os.path.exists, output_path))


async def download_tiktok_video(url: str) -> str | None:
    """
    دانلود ویدیوی تیک‌تاک:
    ۱. دانلود سریع از TikWM API (مستقیم).
    ۲. در صورت خطای کلادفلر، دانلود از SaveTik / TikVid با primp (بدون نیاز به مرورگر).
    ۳. بای‌پاس TikWM با Byparr / FlareSolverr.
    ۴. فال‌بک نهایی به yt-dlp.
    """
    logger.info("[TikTok] Start downloading: %s", url)
    clean_url = url.strip()
    req_id = uuid.uuid4().hex
    output_path = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.mp4")

    proxy = _get_proxy()

    # ۱. روش مستقیم از TikWM API (بدون معطلی سالور)
    try:
        if await _try_tikwm_download(clean_url, output_path, proxy=proxy, allow_solver=False):
            logger.info("[TikTok] Download completed successfully via TikWM API (%s bytes)", await asyncio.to_thread(os.path.getsize, output_path))
            return output_path
    except Exception as e:
        logger.warning("[TikTok] TikWM direct download pipeline exception: %s", e)

    # ۲. روش سریع جایگزین با SaveTik / TikVid (primp)
    try:
        ajax_links = await _fetch_ajax_downloader_urls(clean_url, proxy=proxy)
        if not ajax_links and proxy:
            ajax_links = await _fetch_ajax_downloader_urls(clean_url, proxy=None)

        for dl_url, referer in ajax_links:
            downloaded = await _download_stream_to_file(
                dl_url, output_path, proxy=proxy, referer=referer
            )
            if not downloaded and proxy:
                downloaded = await _download_stream_to_file(
                    dl_url, output_path, proxy=None, referer=referer
                )
            if downloaded and await asyncio.to_thread(os.path.exists, output_path):
                logger.info(
                    "[TikTok] Download completed successfully via SaveTik/TikVid (%s bytes)",
                    await asyncio.to_thread(os.path.getsize, output_path),
                )
                return output_path
    except Exception as e:
        logger.warning("[TikTok] SaveTik/TikVid download pipeline exception: %s", e)

    # ۳. بای‌پاس TikWM با Byparr / FlareSolverr (بدون تکرار درخواست مستقیم ناموفق)
    try:
        if await _try_tikwm_download(clean_url, output_path, proxy=proxy, allow_solver=True, solver_only=True):
            logger.info("[TikTok] Download completed via Byparr/FlareSolverr (%s bytes)", await asyncio.to_thread(os.path.getsize, output_path))
            return output_path
    except Exception as e:
        logger.warning("[TikTok] TikWM solver download pipeline exception: %s", e)

    # ۴. فال‌بک به yt-dlp
    logger.info("[TikTok] Falling back to yt-dlp...")
    if proxy:
        file_path = await _exec_ytdlp_download(clean_url, proxy=proxy)
        if file_path:
            return file_path
        logger.warning("[TikTok] yt-dlp with proxy '%s' failed. Retrying direct yt-dlp...", proxy)

    file_path = await _exec_ytdlp_download(clean_url, proxy=None)
    if file_path:
        return file_path

    logger.error("[TikTok] All download attempts failed for URL: %s", clean_url)
    return None


async def search_tiktok_videos(query: str, max_results: int = 10):
    """
    جستجوی ویدیو در تیک‌تاک با انکودینگ کامل، تست مستقیم POST/GET
    و بای‌پاس کلادفلر (Cloudflare 403) با استفاده از FlareSolverr.
    """
    import hashlib

    clean_query = query.strip()
    if not clean_query:
        return []

    q_hash = hashlib.md5(f"{clean_query.lower()}:{max_results}".encode("utf-8")).hexdigest()[:16]
    cache_key = f"tiktok:search:{q_hash}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list) and cached:
        return cached

    results = []
    cf_blocked = False
    session = await get_http_session()
    endpoints = [
        "https://www.tikwm.com/api/feed/search",
        "https://tikwm.com/api/feed/search",
    ]
    proxy = _get_proxy()
    kwargs = {"headers": DEFAULT_HEADERS, "timeout": aiohttp.ClientTimeout(total=15)}
    if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
        kwargs["proxy"] = proxy

    async with TIKWM_API_SEMAPHORE:
        await _pace_tikwm_request()

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
                                break
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
                                break
                    elif response.status == 403:
                        cf_blocked = True
                        logger.warning("[TikTok] GET search HTTP 403 (Cloudflare) from %s", endpoint)
                    else:
                        logger.warning("[TikTok] GET search HTTP %s from %s", response.status, endpoint)
            except Exception as e:
                logger.warning("[TikTok] GET search error on %s: %s", endpoint, e)

    if results:
        await cache_set(cache_key, results, ttl_sec=180)
        return results

    # روش ۳: استفاده از Byparr / FlareSolverr خارج از سمافور TikWM تا بقیه درخواست‌ها بلاک نشوند
    if cf_blocked or not results:
        logger.info("[TikTok] Attempting Byparr/FlareSolverr bypass for Cloudflare 403 challenge on query '%s'...", clean_query)

        target_url = "https://www.tikwm.com/api/feed/search"
        encoded_query = urllib.parse.quote(clean_query)
        target_get_url = f"{target_url}?keywords={encoded_query}&count={max_results}&cursor=0&web=1"

        # اول درخواست GET (سازگار با Byparr و بدون پارامتر منسوخ headers)
        solution = await flaresolverr_request(
            url=target_get_url,
            method="GET",
            timeout=60,
        )

        # اگر GET پاسخ نداد، POST را بدون headers امتحان می‌کنیم
        if not solution:
            post_payload = f"keywords={encoded_query}&count={max_results}&cursor=0&web=1"
            solution = await flaresolverr_request(
                url=target_url,
                method="POST",
                post_data=post_payload,
                timeout=60,
            )

        if solution and solution.get("response"):
            raw_resp = solution["response"]
            data = _extract_json_data(raw_resp)
            if data:
                results = _parse_tikwm_search_response(data, max_results)
                if results:
                    logger.info("[TikTok] Byparr/FlareSolverr successfully retrieved %s search results for '%s'", len(results), clean_query)
                    await cache_set(cache_key, results, ttl_sec=180)
                    return results
            else:
                logger.error("[TikTok] Byparr/FlareSolverr response could not be parsed as JSON: %s", raw_resp[:300])

    if not results:
        logger.error(
            "[TikTok] Search failed for query '%s': Direct requests got Cloudflare 403 and Byparr/FlareSolverr did not return results. "
            "Ensure Byparr/FlareSolverr container is running on port 8191.",
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
    """گرفتن ویدیوهای ترند تیک‌تاک با پشتیبانی بای‌پاس کلادفلر FlareSolverr و کش کوتاه‌مدت"""
    cache_key = f"tiktok:trends:{count}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list) and cached:
        return cached

    results = []
    cf_blocked = False
    session = await get_http_session()
    endpoints = [
        f"https://www.tikwm.com/api/feed/list?region=US&count={count}",
        f"https://tikwm.com/api/feed/list?region=US&count={count}",
    ]
    proxy = _get_proxy()
    kwargs = {"headers": DEFAULT_HEADERS, "timeout": aiohttp.ClientTimeout(total=15)}
    if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
        kwargs["proxy"] = proxy

    async with TIKWM_API_SEMAPHORE:
        await _pace_tikwm_request()

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
                                await cache_set(cache_key, results, ttl_sec=300)
                                return results
                    elif response.status == 403:
                        cf_blocked = True
                        logger.warning("[TikTok] Trends HTTP 403 (Cloudflare) from %s", url)

            except Exception as e:
                logger.warning("[TikTok] Trends API Error for %s: %s", url, e)

    # تلاش با Byparr / FlareSolverr خارج از سمافور TikWM
    if cf_blocked or not results:
        target_url = f"https://www.tikwm.com/api/feed/list?region=US&count={count}"
        solution = await flaresolverr_request(url=target_url, method="GET", timeout=60)

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
                    await cache_set(cache_key, results, ttl_sec=300)
                    return results

    return results
