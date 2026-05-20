# services/web_scraper.py

import asyncio
import os
import time
from ddgs import (
    DDGS,
)  # در صورت خطا در ایمپورت، این خط جایگزین from ddgs شد

# محدودکننده برای جلوگیری از هنگ کردن سرور هنگام رندر همزمان صفحات سنگین
SINGLEFILE_SEMAPHORE = asyncio.Semaphore(4)

_SINGLEFILE_COMMUNICATE_TIMEOUT = 90.0


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
    for attempt in range(max_attempts):
        async with SINGLEFILE_SEMAPHORE:
            command = [
                "single-file",
                '--browser-args=["--no-sandbox", "--disable-setuid-sandbox"]',
                url,
                output_path,
            ]

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
                err_msg = stderr.decode() if stderr else "Unknown Error"
                print(
                    f"SingleFile failed (attempt {attempt + 1}/{max_attempts}). Error: {err_msg}"
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
