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
from services.cache_service import cache_delete, cache_get, cache_set
from services.http_client import get_http_session
from services.flaresolverr import flaresolverr_request
from services.youtube import get_ytdlp_executable

load_dotenv()

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TIKWM_API_SEMAPHORE = asyncio.Semaphore(2)
TIKWM_SEARCH_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("TIKTOK_SEARCH_CONCURRENT", "3"))))
_TIKTOK_YTDLP_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("TIKTOK_YTDLP_CONCURRENT", "3"))))
_AJAX_DOWNLOADER_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("TIKTOK_AJAX_CONCURRENT", "3"))))
_TIKTOK_MAX_BYTES = int(os.getenv("TIKTOK_MAX_BYTES", str(512 * 1024 * 1024)))
_TIKWM_MIN_INTERVAL_SEC = max(0.2, float(os.getenv("TIKWM_MIN_INTERVAL_SEC", "1.05")))
_TIKWM_SEARCH_CACHE_TTL = max(60, int(os.getenv("TIKTOK_SEARCH_CACHE_TTL", "900")))
_TIKWM_TRENDS_CACHE_TTL = max(60, int(os.getenv("TIKTOK_TRENDS_CACHE_TTL", "900")))
_TIKWM_CF_CACHE_TTL = max(120, int(os.getenv("TIKWM_CF_CACHE_TTL", "1200")))
_TIKWM_CF_CACHE_KEY = "tiktok:tikwm:cf_session"
_TIKWM_PRIMARY_HOST = "https://www.tikwm.com"

_tikwm_last_call = 0.0
_tikwm_rate_lock = asyncio.Lock()
_tikwm_cf_solve_task: asyncio.Task | None = None
_inflight_tt_search: dict[str, asyncio.Task] = {}
_inflight_tt_trends: dict[int, asyncio.Task] = {}
_cookie_exists_cache: dict[str, tuple[bool, float]] = {}


def _cookie_file_exists_sync(path: str) -> bool:
    now = time.monotonic()
    cached = _cookie_exists_cache.get(path)
    if cached is not None and cached[1] > now:
        return cached[0]
    exists = os.path.exists(path)
    _cookie_exists_cache[path] = (exists, now + 60.0)
    return exists


async def _pace_tikwm_request(min_interval: float | None = None) -> None:
    global _tikwm_last_call
    interval = _TIKWM_MIN_INTERVAL_SEC if min_interval is None else min_interval
    async with _tikwm_rate_lock:
        now = time.monotonic()
        wait = interval - (now - _tikwm_last_call)
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


async def _get_cached_cf_session() -> dict | None:
    cached = await cache_get(_TIKWM_CF_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("cookie_header"):
        return cached
    return None


async def _save_cf_session_from_solution(solution: dict | None) -> dict | None:
    if not isinstance(solution, dict):
        return None
    cookies = solution.get("cookies") or []
    parts: list[str] = []
    if isinstance(cookies, list):
        for c in cookies:
            if isinstance(c, dict) and c.get("name") and c.get("value") is not None:
                parts.append(f"{c['name']}={c['value']}")
    cookie_header = "; ".join(parts)
    if not cookie_header:
        return None
    cf_session = {
        "cookie_header": cookie_header,
        "user_agent": solution.get("userAgent") or DEFAULT_HEADERS["User-Agent"],
    }
    await cache_set(_TIKWM_CF_CACHE_KEY, cf_session, ttl_sec=_TIKWM_CF_CACHE_TTL)
    return cf_session


async def _clear_cached_cf_session() -> None:
    await cache_delete(_TIKWM_CF_CACHE_KEY)


def _build_tikwm_headers(cf_session: dict | None = None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if isinstance(cf_session, dict):
        if cf_session.get("user_agent"):
            headers["User-Agent"] = str(cf_session["user_agent"])
        if cf_session.get("cookie_header"):
            headers["Cookie"] = str(cf_session["cookie_header"])
    return headers


def _is_tikwm_rate_limited(data: dict | list | None) -> bool:
    if not isinstance(data, dict) or data.get("code") == 0:
        return False
    msg = str(data.get("msg") or data.get("message") or "").lower()
    return any(tok in msg for tok in ("limit", "frequent", "too many", "rate"))


def _extract_direct_video_url(item: dict | None) -> str | None:
    if not isinstance(item, dict):
        return None
    video_url = item.get("hdplay") or item.get("play") or item.get("wmplay")
    if not isinstance(video_url, str):
        return None
    video_url = video_url.strip()
    if not video_url:
        return None
    if video_url.startswith("/"):
        return f"{_TIKWM_PRIMARY_HOST}{video_url}"
    if video_url.startswith(("http://", "https://")):
        return video_url
    return None


async def _primp_tikwm_request(
    method: str,
    url: str,
    *,
    post_data: dict | None = None,
    proxy: str | None = None,
    timeout_sec: float = 8.0,
) -> tuple[int, str | None]:
    try:
        import primp
    except ImportError:
        return (0, None)

    def _run_sync() -> tuple[int, str | None]:
        client, client_lock = _get_primp_client(primp, proxy)
        with client_lock:
            try:
                if method.upper() == "POST":
                    resp = client.post(
                        url,
                        data=post_data,
                        headers=DEFAULT_HEADERS,
                        timeout=timeout_sec,
                    )
                else:
                    resp = client.get(
                        url,
                        headers=DEFAULT_HEADERS,
                        timeout=timeout_sec,
                    )
                return (int(resp.status_code), resp.text)
            except Exception as exc:
                logger.warning("[TikTok] primp TikWM %s error on %s: %s", method, url, exc)
                return (0, None)

    return await asyncio.to_thread(_run_sync)


async def _aiohttp_tikwm_once(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    post_data: dict | None = None,
    headers: dict[str, str],
    proxy: str | None = None,
    timeout_sec: float = 8.0,
) -> tuple[int, str | None]:
    kwargs: dict = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=timeout_sec),
    }
    if proxy and (proxy.startswith("http://") or proxy.startswith("https://")):
        kwargs["proxy"] = proxy

    try:
        if method.upper() == "POST":
            async with session.post(url, data=post_data, **kwargs) as resp:
                if resp.status == 200:
                    return (200, await resp.text())
                return (resp.status, None)
        else:
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return (200, await resp.text())
                return (resp.status, None)
    except Exception as exc:
        logger.warning("[TikTok] TikWM %s error on %s: %s", method, url, exc)
        return (0, None)


async def _solve_tikwm_with_flaresolverr_singleflight(
    *,
    solver_get_url: str,
    solver_post_url: str | None = None,
    solver_post_body: str | None = None,
    timeout: int = 45,
) -> tuple[dict | None, bool]:
    """
    Solve TikWM Cloudflare challenge via FlareSolverr using singleflight deduplication.
    Returns (solution_dict, is_owner). Non-owners wait for the owner to populate the CF cookie cache.
    """
    global _tikwm_cf_solve_task
    existing = _tikwm_cf_solve_task
    if existing is not None and not existing.done():
        try:
            await asyncio.shield(existing)
        except Exception:
            pass
        return (None, False)

    async def _run_solver() -> dict | None:
        solution = await flaresolverr_request(
            url=solver_get_url,
            method="GET",
            timeout=timeout,
        )
        if not solution and solver_post_url and solver_post_body:
            solution = await flaresolverr_request(
                url=solver_post_url,
                method="POST",
                post_data=solver_post_body,
                timeout=timeout,
            )
        if solution:
            await _save_cf_session_from_solution(solution)
        return solution

    task = asyncio.create_task(_run_solver())
    _tikwm_cf_solve_task = task

    def _cleanup(t: asyncio.Task) -> None:
        global _tikwm_cf_solve_task
        if _tikwm_cf_solve_task is t:
            _tikwm_cf_solve_task = None
        if not t.cancelled():
            try:
                t.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    try:
        sol = await asyncio.shield(task)
        return (sol, True)
    except Exception as exc:
        logger.warning("[TikTok] Byparr/FlareSolverr error: %s", exc)
        return (None, True)


async def _tikwm_request_json(
    endpoint: str,
    *,
    method: str = "POST",
    post_data: dict | None = None,
    query_url: str | None = None,
    solver_get_url: str,
    solver_post_body: str | None = None,
    proxy: str | None = None,
    semaphore: asyncio.Semaphore = TIKWM_SEARCH_SEMAPHORE,
    allow_solver: bool = True,
    solver_only: bool = False,
    timeout_sec: float = 8.0,
) -> tuple[dict | list | None, bool]:
    """
    Fast TikWM JSON requester (skips raw unauthenticated aiohttp which gets Cloudflare 403):
    1. If cached CF cookies/UA exist, use aiohttp directly with them (single retry on rate limit).
    2. Otherwise (or if cached CF cookies expired), use primp TLS impersonation directly.
    3. If primp also gets 403, use singleflight FlareSolverr and cache cf_clearance cookies for 20 min.
    Returns (parsed_json, cf_blocked).
    """
    target_url = endpoint if method.upper() == "POST" else (query_url or endpoint)
    cf_blocked = False

    if not solver_only:
        cf_session = await _get_cached_cf_session()

        async with semaphore:
            if cf_session is not None:
                session = await get_http_session()
                await _pace_tikwm_request()
                status, text_data = await _aiohttp_tikwm_once(
                    session,
                    method,
                    target_url,
                    post_data=post_data,
                    headers=_build_tikwm_headers(cf_session),
                    proxy=proxy,
                    timeout_sec=timeout_sec,
                )
                if status == 200 and text_data:
                    data = _extract_json_data(text_data)
                    if _is_tikwm_rate_limited(data):
                        await asyncio.sleep(1.1)
                        await _pace_tikwm_request()
                        status2, text2 = await _aiohttp_tikwm_once(
                            session,
                            method,
                            target_url,
                            post_data=post_data,
                            headers=_build_tikwm_headers(cf_session),
                            proxy=proxy,
                            timeout_sec=timeout_sec,
                        )
                        if status2 == 200 and text2:
                            return (_extract_json_data(text2), False)
                        return (None, status2 == 403)
                    return (data, False)
                if status == 403:
                    cf_blocked = True
                    logger.warning("[TikTok] TikWM %s HTTP 403 with cached CF cookie on %s; refreshing...", method, endpoint)
                    await _clear_cached_cf_session()
                elif status > 0:
                    logger.warning("[TikTok] TikWM %s HTTP %s from %s", method, status, endpoint)
                    return (None, False)

            if cf_session is None or cf_blocked:
                await _pace_tikwm_request()
                p_status, p_text = await _primp_tikwm_request(
                    method,
                    target_url,
                    post_data=post_data,
                    proxy=proxy,
                    timeout_sec=timeout_sec,
                )
                if p_status == 200 and p_text:
                    data = _extract_json_data(p_text)
                    if _is_tikwm_rate_limited(data):
                        await asyncio.sleep(1.1)
                        await _pace_tikwm_request()
                        p_status2, p_text2 = await _primp_tikwm_request(
                            method,
                            target_url,
                            post_data=post_data,
                            proxy=proxy,
                            timeout_sec=timeout_sec,
                        )
                        if p_status2 == 200 and p_text2:
                            return (_extract_json_data(p_text2), False)
                        return (None, p_status2 == 403)
                    return (data, False)
                if p_status == 403:
                    cf_blocked = True
                    logger.warning("[TikTok] primp TikWM %s HTTP 403 (Cloudflare) from %s", method, endpoint)
                elif p_status > 0:
                    logger.warning("[TikTok] primp TikWM %s HTTP %s from %s", method, p_status, endpoint)
                    cf_blocked = False

    if (cf_blocked or solver_only) and allow_solver:
        logger.info("[TikTok] TikWM blocked by Cloudflare (403), attempting singleflight Byparr/FlareSolverr...")
        solution, is_owner = await _solve_tikwm_with_flaresolverr_singleflight(
            solver_get_url=solver_get_url,
            solver_post_url=endpoint,
            solver_post_body=solver_post_body,
            timeout=45,
        )
        if is_owner and solution and solution.get("response"):
            return (_extract_json_data(solution["response"]), True)

        # Non-owner (or owner with fresh cookies): retry quickly via aiohttp with cached CF cookies
        fresh_cf = await _get_cached_cf_session()
        if fresh_cf:
            session = await get_http_session()
            async with semaphore:
                await _pace_tikwm_request()
                status, text_data = await _aiohttp_tikwm_once(
                    session,
                    method,
                    target_url,
                    post_data=post_data,
                    headers=_build_tikwm_headers(fresh_cf),
                    proxy=proxy,
                    timeout_sec=timeout_sec,
                )
                if status == 200 and text_data:
                    return (_extract_json_data(text_data), False)

    return (None, cf_blocked)


async def _fetch_tikwm_video_info(
    url: str,
    proxy: str | None = None,
    allow_solver: bool = True,
    solver_only: bool = False,
) -> dict | None:
    """دریافت متادیتا و لینک‌های مستقیم دانلود از TikWM API"""
    clean_url = url.strip()
    encoded_url = urllib.parse.quote(clean_url)
    endpoint = f"{_TIKWM_PRIMARY_HOST}/api/"

    data, _ = await _tikwm_request_json(
        endpoint,
        method="POST",
        post_data={"url": clean_url, "hd": "1"},
        solver_get_url=f"{endpoint}?url={encoded_url}&hd=1",
        solver_post_body=f"url={encoded_url}&hd=1",
        proxy=proxy,
        semaphore=TIKWM_API_SEMAPHORE,
        allow_solver=allow_solver,
        solver_only=solver_only,
        timeout_sec=12.0,
    )
    if isinstance(data, dict) and data.get("code") == 0 and data.get("data"):
        return data.get("data")
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
    if await asyncio.to_thread(_cookie_file_exists_sync, cookie_file):
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


async def download_tiktok_video(url: str, direct_url: str | None = None) -> str | None:
    """
    دانلود ویدیوی تیک‌تاک:
    ۰. در صورت وجود لینک مستقیم کش‌شده از نتیجه سرچ/ترند، دانلود فوری بدون تماس مجدد با TikWM API.
    ۱. دانلود سریع از TikWM API (مستقیم / primp / کوکی کش‌شده کلادفلر).
    ۲. در صورت خطا، دانلود از SaveTik / TikVid با primp (بدون نیاز به مرورگر).
    ۳. بای‌پاس TikWM با Byparr / FlareSolverr.
    ۴. فال‌بک نهایی به yt-dlp.
    """
    logger.info("[TikTok] Start downloading: %s", url)
    clean_url = url.strip()
    req_id = uuid.uuid4().hex
    output_path = os.path.join(DOWNLOAD_DIR, f"tt_{req_id}.mp4")

    proxy = _get_proxy()

    # ۰. دانلود فوری با لینک مستقیم موجود از نتیجه سرچ/ترند (صرفه‌جویی در سهمیه TikWM)
    if direct_url and isinstance(direct_url, str) and direct_url.startswith(("http://", "https://")):
        try:
            downloaded = await _download_stream_to_file(direct_url, output_path, proxy=proxy)
            if not downloaded and proxy:
                downloaded = await _download_stream_to_file(direct_url, output_path, proxy=None)
            if downloaded and await asyncio.to_thread(os.path.exists, output_path):
                logger.info(
                    "[TikTok] Download completed directly from cached search/trend URL (%s bytes)",
                    await asyncio.to_thread(os.path.getsize, output_path),
                )
                return output_path
        except Exception as e:
            logger.warning("[TikTok] Direct cached URL download failed, falling back: %s", e)

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
    جستجوی سریع ویدیو در تیک‌تاک:
    - کش ۱۵ دقیقه‌ای با نرمال‌سازی کوئری + singleflight
    - ارسال یک درخواست مستقیم (با کوکی کلادفلر کش‌شده در صورت وجود)
    - فال‌بک سریع به primp (جعل TLS مرورگر بدون مرورگر هدلس)
    - فال‌بک نهایی singleflight به FlareSolverr با کش کوکی cf_clearance
    """
    import hashlib

    clean_query = re.sub(r"\s+", " ", (query or "")).strip()
    if not clean_query:
        return []

    q_hash = hashlib.md5(f"{clean_query.lower()}:{max_results}".encode("utf-8")).hexdigest()[:16]
    cache_key = f"tiktok:search:{q_hash}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list) and cached:
        return cached

    existing = _inflight_tt_search.get(cache_key)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    async def _do_search():
        endpoint = f"{_TIKWM_PRIMARY_HOST}/api/feed/search"
        encoded_query = urllib.parse.quote(clean_query)
        solver_get_url = f"{endpoint}?keywords={encoded_query}&count={max_results}&cursor=0&web=1"
        solver_post_body = f"keywords={encoded_query}&count={max_results}&cursor=0&web=1"
        post_data = {
            "keywords": clean_query,
            "count": str(max_results),
            "cursor": "0",
            "web": "1",
        }

        data, cf_blocked = await _tikwm_request_json(
            endpoint,
            method="POST",
            post_data=post_data,
            solver_get_url=solver_get_url,
            solver_post_body=solver_post_body,
            proxy=_get_proxy(),
            semaphore=TIKWM_SEARCH_SEMAPHORE,
            allow_solver=True,
            timeout_sec=8.0,
        )

        results = _parse_tikwm_search_response(data, max_results) if data else []
        if results:
            await cache_set(cache_key, results, ttl_sec=_TIKWM_SEARCH_CACHE_TTL)
            return results

        if cf_blocked:
            logger.error(
                "[TikTok] Search failed for query '%s': Direct/primp requests got Cloudflare 403 and Byparr/FlareSolverr did not return results. "
                "Ensure Byparr/FlareSolverr container is running on port 8191.",
                clean_query,
            )

        return results

    task = asyncio.create_task(_do_search())
    _inflight_tt_search[cache_key] = task

    def _cleanup(t: asyncio.Task) -> None:
        if _inflight_tt_search.get(cache_key) is t:
            _inflight_tt_search.pop(cache_key, None)
        if not t.cancelled():
            try:
                t.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)


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
        entry = {"title": title, "url": link}
        direct_url = _extract_direct_video_url(item)
        if direct_url:
            entry["direct_url"] = direct_url

        results.append(entry)

        if len(results) >= max_results:
            break

    return results


def _parse_tikwm_trends_response(data: dict, count: int) -> list:
    results = []
    if not isinstance(data, dict) or data.get("code") != 0:
        return results

    data_block = data.get("data")
    videos = []
    if isinstance(data_block, list):
        videos = data_block
    elif isinstance(data_block, dict):
        videos = data_block.get("videos") or data_block.get("list") or []

    if not isinstance(videos, list):
        return results

    for item in videos:
        if not isinstance(item, dict):
            continue

        title = item.get("title") or item.get("desc") or "Trending video"
        video_id = item.get("video_id") or item.get("id")
        if not video_id:
            continue

        author_data = item.get("author")
        if isinstance(author_data, dict):
            author = author_data.get("unique_id", "user")
        else:
            author = "user"

        link = f"https://www.tiktok.com/@{author}/video/{video_id}"
        entry = {"title": title, "url": link}
        direct_url = _extract_direct_video_url(item)
        if direct_url:
            entry["direct_url"] = direct_url

        results.append(entry)
        if len(results) >= count:
            break

    return results


async def get_tiktok_trends(count: int = 10):
    """گرفتن ویدیوهای ترند تیک‌تاک با کش ۱۵ دقیقه‌ای، primp و کش کوکی کلادفلر"""
    cache_key = f"tiktok:trends:{count}"
    cached = await cache_get(cache_key)
    if isinstance(cached, list) and cached:
        return cached

    existing = _inflight_tt_trends.get(count)
    if existing is not None and not existing.done():
        return await asyncio.shield(existing)

    async def _do_trends():
        target_url = f"{_TIKWM_PRIMARY_HOST}/api/feed/list?region=US&count={count}"
        data, _ = await _tikwm_request_json(
            target_url,
            method="GET",
            query_url=target_url,
            solver_get_url=target_url,
            proxy=_get_proxy(),
            semaphore=TIKWM_SEARCH_SEMAPHORE,
            allow_solver=True,
            timeout_sec=8.0,
        )
        results = _parse_tikwm_trends_response(data, count) if data else []
        if results:
            await cache_set(cache_key, results, ttl_sec=_TIKWM_TRENDS_CACHE_TTL)
        return results

    task = asyncio.create_task(_do_trends())
    _inflight_tt_trends[count] = task

    def _cleanup(t: asyncio.Task) -> None:
        if _inflight_tt_trends.get(count) is t:
            _inflight_tt_trends.pop(count, None)
        if not t.cancelled():
            try:
                t.exception()
            except Exception:
                pass

    task.add_done_callback(_cleanup)
    return await asyncio.shield(task)
