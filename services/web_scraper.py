# services/web_scraper.py

import asyncio
import json
import os
import shutil
import time
from typing import List, Optional

from ddgs import (
    DDGS,
)  # در صورت خطا در ایمپورت، این خط جایگزین from ddgs شد

from services.chromium_workload import heavy_chromium_semaphore

# محدودکنندهٔ قبلی حذف شد؛ Pinterest و SingleFile همین سمافور را share می‌کنند.
_SINGLEFILE_COMMUNICATE_TIMEOUT = 90.0

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


def _get_singlefile_browser_executable() -> Optional[str]:
    """
    مسیر اجرایی کروم/کرومیوم برای single-file-cli.
    بدون مرورگر سیستمی، بستهٔ npm گاهی Chromium را درست اجرا نمی‌کند و با کد ۲۱ خارج می‌شود.
    """
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


def search_web(query, max_results=10, max_attempts=3):
    """جستجو در وب؛ با چند بار تلاش برای خطای محدودیت/شبکه DuckDuckGo."""
    for attempt in range(max_attempts):
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({"title": r["title"], "url": r["href"]})
            if results:
                return results
        except Exception as e:
            print(f"Search Error (attempt {attempt + 1}/{max_attempts}): {e}")
        if attempt < max_attempts - 1:
            time.sleep(1.0 * (attempt + 1))
    return []


async def create_single_file(url, output_path, max_attempts=3):
    """اجرای غیرهمزمان ابزار SingleFile CLI با تکرار در صورت شکست."""
    global _BROWSER_MISSING_LOGGED
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
                "single-file",
                f"--browser-args={browser_args_json}",
                url,
                output_path,
            ]
            if browser_exe:
                command.insert(1, f"--browser-executable-path={browser_exe}")

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=_SINGLEFILE_COMMUNICATE_TIMEOUT,
                )
                if process.returncode == 0 and os.path.exists(output_path):
                    return True
                err_msg = stderr.decode(errors="replace") if stderr else "Unknown Error"
                out_msg = stdout.decode(errors="replace") if stdout else ""
                if out_msg.strip():
                    print(f"SingleFile stdout: {out_msg[:2000]}")
                print(
                    f"SingleFile failed (attempt {attempt + 1}/{max_attempts}, "
                    f"browser={browser_exe or 'default bundled'}). Error: {err_msg}"
                )

            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                print(f"SingleFile timeout for URL: {url} (attempt {attempt + 1})")
            except Exception as e:
                print(f"SingleFile error: {e}")

            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError:
                pass

        if attempt < max_attempts - 1:
            await asyncio.sleep(1.5 * (attempt + 1))

    return False
