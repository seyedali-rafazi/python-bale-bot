# services/web_scraper.py

import asyncio
from functools import lru_cache
import json
import logging
import os
import shutil
import signal
import sys
import time
from typing import List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

import aiohttp
from bs4 import BeautifulSoup
from ddgs import (
    DDGS,
)  # در صورت خطا در ایمپورت، این خط جایگزین from ddgs شد

from services.chromium_workload import heavy_chromium_semaphore
from services.http_client import get_http_session
from services.playwright_browser_manager import get_browser_manager

# محدودکنندهٔ قبلی حذف شد؛ Pinterest و SingleFile همین سمافور را share می‌کنند.
_SINGLEFILE_COMMUNICATE_TIMEOUT = 90.0
_PLAYWRIGHT_PAGE_TIMEOUT_MS = 45_000
_PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MAX_INLINED_STYLESHEETS = 20
_MAX_STYLESHEET_BYTES = 512 * 1024
_MAX_TOTAL_CSS_BYTES = 4 * 1024 * 1024

# آرگومان‌های مرورگر برای سرور لینوکس / Docker (کاهش خروج Chromium با کد ۲۱)
_DEFAULT_BROWSER_ARGS: List[str] = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--no-first-run",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--mute-audio",
]


_BROWSER_MISSING_LOGGED = False
_SINGLEFILE_MISSING_LOGGED = False


def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    """Kill SingleFile and any Chrome child processes it spawned."""
    if process.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


@lru_cache(maxsize=1)
def _find_singlefile_executable_cached() -> Optional[str]:
    """Locate the single-file CLI binary from env, PATH, or common npm paths (cached)."""
    for key in ("SINGLEFILE_PATH", "SINGLEFILE_BIN", "SINGLEFILE_CLI_PATH"):
        p = os.environ.get(key, "").strip()
        if p and os.path.isfile(p) and (sys.platform == "win32" or os.access(p, os.X_OK)):
            return p

    for name in ("single-file", "single-file.cmd"):
        p = shutil.which(name)
        if p:
            return p

    candidates = [
        os.path.join(os.getcwd(), "node_modules", ".bin", "single-file"),
        os.path.join(os.getcwd(), "node_modules", ".bin", "single-file.cmd"),
        "/usr/local/bin/single-file",
        "/usr/bin/single-file",
        os.path.expanduser("~/.npm-global/bin/single-file"),
        os.path.expanduser("~/.local/bin/single-file"),
    ]
    for path in candidates:
        if os.path.isfile(path) and (sys.platform == "win32" or os.access(path, os.X_OK)):
            return path

    return None


def _get_singlefile_executable() -> Optional[str]:
    """Locate the single-file CLI binary from env, PATH, or common npm paths."""
    return _find_singlefile_executable_cached()


@lru_cache(maxsize=1)
def _find_singlefile_browser_executable_cached() -> Optional[str]:
    for key in (
        "SINGLEFILE_BROWSER_PATH",
        "SINGLEFILE_CHROME_PATH",
        "CHROME_PATH",
        "CHROMIUM_PATH",
        "GOOGLE_CHROME_BIN",
    ):
        p = os.environ.get(key, "").strip()
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    for name in (
        "google-chrome-stable",
        "google-chrome",
        "chromium-browser",
        "chromium",
        "chrome",
    ):
        p = shutil.which(name)
        if p:
            return p

    for path in (
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


def _get_singlefile_browser_executable() -> Optional[str]:
    """
    مسیر اجرایی کروم/کرومیوم برای single-file-cli.
    بدون مرورگر سیستمی، بستهٔ npm گاهی Chromium را درست اجرا نمی‌کند و با کد ۲۱ خارج می‌شود.
    """
    return _find_singlefile_browser_executable_cached()


def _search_web_once(query: str, max_results: int = 10) -> list:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({"title": r["title"], "url": r["href"]})
    return results


def search_web(query, max_results=10, max_attempts=3):
    """جستجو در وب؛ با چند بار تلاش برای خطای محدودیت/شبکه DuckDuckGo."""
    for attempt in range(max_attempts):
        try:
            results = _search_web_once(query, max_results=max_results)
            if results:
                return results
        except Exception as e:
            logger.warning("Search Error (attempt %s/%s): %s", attempt + 1, max_attempts, e)
        if attempt < max_attempts - 1:
            time.sleep(1.0 * (attempt + 1))
    return []


_ORIG_SEARCH_WEB = search_web


async def async_search_web(query: str, max_results: int = 10, max_attempts: int = 3) -> list:
    """Async cached web search with non-blocking retries and timeout protection."""
    import hashlib
    from services.cache_service import cache_get, cache_set

    clean_q = (query or "").strip()
    cache_key = None
    if clean_q:
        q_hash = hashlib.md5(clean_q.lower().encode("utf-8")).hexdigest()[:16]
        cache_key = f"web_search:{max_results}:{q_hash}"
        cached = await cache_get(cache_key)
        if isinstance(cached, list) and cached:
            return cached

    if search_web is not _ORIG_SEARCH_WEB:
        results = await asyncio.wait_for(
            asyncio.to_thread(search_web, query, max_results, max_attempts),
            timeout=35.0,
        )
    else:
        results = []
        deadline = asyncio.get_running_loop().time() + 35.0
        for attempt in range(max_attempts):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                results = await asyncio.wait_for(
                    asyncio.to_thread(_search_web_once, query, max_results),
                    timeout=remaining,
                )
                if results:
                    break
            except asyncio.TimeoutError:
                break
            except Exception as e:
                logger.warning(
                    "Search Error (attempt %s/%s): %s", attempt + 1, max_attempts, e
                )
            if attempt < max_attempts - 1:
                delay = min(1.0 * (attempt + 1), max(0.0, deadline - asyncio.get_running_loop().time()))
                if delay <= 0:
                    break
                await asyncio.sleep(delay)

    if cache_key and results:
        await cache_set(cache_key, results, ttl_sec=900)
    return results


def _remove_file_if_exists(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


async def _fetch_stylesheet_text(
    session: aiohttp.ClientSession, css_url: str
) -> Optional[str]:
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        headers = {"User-Agent": _PLAYWRIGHT_USER_AGENT}
        async with session.get(css_url, timeout=timeout, headers=headers) as resp:
            if resp.status != 200:
                return None
            raw = await resp.content.read(_MAX_STYLESHEET_BYTES + 1)
            if len(raw) > _MAX_STYLESHEET_BYTES:
                return None
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _prepare_soup_and_collect_css(
    html_content: str, base_url: str
) -> tuple[BeautifulSoup, list[tuple[object, str]]]:
    soup = BeautifulSoup(html_content, "html.parser")

    for script_tag in soup.find_all("script"):
        script_tag.decompose()

    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    if head.find("base") is None:
        base_tag = soup.new_tag("base", href=base_url)
        head.insert(0, base_tag)

    if head.find("meta", attrs={"charset": True}) is None:
        head.insert(0, soup.new_tag("meta", charset="utf-8"))

    css_links = []
    for link in soup.find_all("link", href=True):
        rel_values = [r.lower() for r in (link.get("rel") or [])]
        if "stylesheet" in rel_values:
            abs_href = urljoin(base_url, link["href"])
            if abs_href.startswith(("http://", "https://")):
                css_links.append((link, abs_href))
            if len(css_links) >= _MAX_INLINED_STYLESHEETS:
                break

    return soup, css_links


def _apply_css_and_serialize(
    soup: BeautifulSoup,
    css_links: list[tuple[object, str]],
    fetched_styles: list,
) -> str:
    total_css_bytes = 0
    for (link_tag, href), css_text in zip(css_links, fetched_styles):
        if not isinstance(css_text, str) or not css_text.strip():
            continue
        css_size = len(css_text.encode("utf-8", errors="replace"))
        if total_css_bytes + css_size > _MAX_TOTAL_CSS_BYTES:
            continue
        total_css_bytes += css_size
        safe_css = css_text.replace("</style", "<\\/style").replace("</STYLE", "<\\/STYLE")
        style_tag = soup.new_tag("style")
        style_tag["data-source-href"] = href
        style_tag.string = safe_css
        link_tag.replace_with(style_tag)

    return str(soup)


async def _inline_stylesheets_and_prepare_html(
    html_content: str, base_url: str
) -> str:
    """Prepare a standalone HTML snapshot by stripping scripts, setting <base>, and inlining CSS."""
    soup, css_links = await asyncio.to_thread(
        _prepare_soup_and_collect_css, html_content, base_url
    )

    if css_links:
        session = await get_http_session()
        fetched_styles = await asyncio.gather(
            *(_fetch_stylesheet_text(session, href) for _, href in css_links),
            return_exceptions=True,
        )
        return await asyncio.to_thread(
            _apply_css_and_serialize, soup, css_links, fetched_styles
        )

    return await asyncio.to_thread(str, soup)


async def _create_single_file_with_playwright(
    url: str, output_path: str, max_attempts: int = 2
) -> bool:
    """Fallback webpage saver using the shared Playwright Chromium browser."""
    manager = get_browser_manager()

    for attempt in range(max_attempts):
        try:
            async with heavy_chromium_semaphore:
                context = None
                page = None
                try:
                    context = await manager.new_context(_PLAYWRIGHT_USER_AGENT)
                    page = await context.new_page()

                    async def _block_media(route):
                        if route.request.resource_type == "media":
                            await route.abort()
                        else:
                            await route.continue_()

                    await page.route("**/*", _block_media)
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=_PLAYWRIGHT_PAGE_TIMEOUT_MS,
                    )
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass

                    final_url = page.url or url
                    html_content = await page.content()
                finally:
                    if page is not None:
                        try:
                            await page.close()
                        except Exception:
                            pass
                    if context is not None:
                        try:
                            await context.close()
                        except Exception:
                            pass

            if not html_content or not html_content.strip():
                raise ValueError("Empty HTML returned by Playwright")

            standalone_html = await _inline_stylesheets_and_prepare_html(
                html_content, final_url
            )
            def _write_html_sync():
                parent_dir = os.path.dirname(output_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(standalone_html)

            await asyncio.to_thread(_write_html_sync)

            if await asyncio.to_thread(lambda: os.path.exists(output_path) and os.path.getsize(output_path) > 0):
                return True
        except Exception as e:
            print(
                f"Playwright SingleFile fallback failed "
                f"(attempt {attempt + 1}/{max_attempts}) for {url}: {e}"
            )
            await asyncio.to_thread(_remove_file_if_exists, output_path)

        if attempt < max_attempts - 1:
            await asyncio.sleep(1.5 * (attempt + 1))

    return False


async def _run_singlefile_cli(
    singlefile_exe: str, url: str, output_path: str, max_attempts: int
) -> bool:
    """Run the external single-file CLI with retries and timeout protection."""
    global _BROWSER_MISSING_LOGGED, _SINGLEFILE_MISSING_LOGGED
    browser_exe = _get_singlefile_browser_executable()
    browser_args_json = json.dumps(_DEFAULT_BROWSER_ARGS, separators=(",", ":"))

    if not browser_exe and not _BROWSER_MISSING_LOGGED:
        print(
            "SingleFile: هیچ Chrome/Chromium سیستمی پیدا نشد. "
            "برای جلوگیری از خطای کد ۲۱، chromium نصب کنید یا متغیر "
            "SINGLEFILE_BROWSER_PATH را به مسیر اجرایی مرورگر تنظیم کنید."
        )
        _BROWSER_MISSING_LOGGED = True

    for attempt in range(max_attempts):
        async with heavy_chromium_semaphore:
            command = [
                singlefile_exe,
                f"--browser-args={browser_args_json}",
                url,
                output_path,
            ]
            if browser_exe:
                command.insert(1, f"--browser-executable-path={browser_exe}")

            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=(sys.platform != "win32"),
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=_SINGLEFILE_COMMUNICATE_TIMEOUT,
                )
                if process.returncode == 0 and await asyncio.to_thread(os.path.exists, output_path):
                    return True
                err_msg = (
                    stderr.decode(errors="replace") if stderr else "Unknown Error"
                )
                out_msg = stdout.decode(errors="replace") if stdout else ""
                if out_msg.strip():
                    print(f"SingleFile stdout: {out_msg[:2000]}")
                print(
                    f"SingleFile failed (attempt {attempt + 1}/{max_attempts}, "
                    f"browser={browser_exe or 'default bundled'}). Error: {err_msg}"
                )
            except FileNotFoundError:
                if not _SINGLEFILE_MISSING_LOGGED:
                    print(
                        f"SingleFile binary not found at '{singlefile_exe}'. "
                        "Falling back to Playwright."
                    )
                    _SINGLEFILE_MISSING_LOGGED = True
                await asyncio.to_thread(_remove_file_if_exists, output_path)
                return False
            except asyncio.CancelledError:
                if process is not None and process.returncode is None:
                    _terminate_process_tree(process)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                    except Exception:
                        pass
                await asyncio.to_thread(_remove_file_if_exists, output_path)
                raise
            except asyncio.TimeoutError:
                if process is not None:
                    _terminate_process_tree(process)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                    except Exception:
                        pass
                print(f"SingleFile timeout for URL: {url} (attempt {attempt + 1})")
            except Exception as e:
                if process is not None and process.returncode is None:
                    _terminate_process_tree(process)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                    except Exception:
                        pass
                print(f"SingleFile error: {e}")

            await asyncio.to_thread(_remove_file_if_exists, output_path)

        if attempt < max_attempts - 1:
            await asyncio.sleep(1.5 * (attempt + 1))

    return False


async def create_single_file(url, output_path, max_attempts=3):
    """اجرای غیرهمزمان ابزار SingleFile CLI با تکرار در صورت شکست و fallback به Playwright."""
    global _SINGLEFILE_MISSING_LOGGED
    singlefile_exe = _get_singlefile_executable()

    if singlefile_exe:
        if await _run_singlefile_cli(singlefile_exe, url, output_path, max_attempts):
            return True
    elif not _SINGLEFILE_MISSING_LOGGED:
        print(
            "SingleFile CLI ('single-file') در سرور یافت نشد؛ استفاده از Playwright fallback. "
            "(برای نصب اختیاری CLI: npm install -g single-file-cli یا تنظیم SINGLEFILE_PATH)"
        )
        _SINGLEFILE_MISSING_LOGGED = True

    return await _create_single_file_with_playwright(
        url, output_path, max_attempts=min(max_attempts, 2)
    )
