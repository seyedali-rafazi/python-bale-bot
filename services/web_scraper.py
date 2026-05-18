# services/web_scraper.py

import asyncio
import os
import time
from ddgs import DDGS

# محدودکننده برای جلوگیری از هنگ کردن سرور هنگام رندر همزمان صفحات سنگین
SINGLEFILE_SEMAPHORE = asyncio.Semaphore(5)


def search_web(query, max_results=10):
    """جستجو در وب بدون بلاک کردن"""
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({"title": r["title"], "url": r["href"]})
    except Exception as e:
        print(f"Search Error: {e}")
    return results


async def create_single_file(url, output_path):
    """اجرای غیرهمزمان ابزار SingleFile CLI"""
    async with SINGLEFILE_SEMAPHORE:
        # استفاده از دستور single-file با تایم‌اوت برای جلوگیری از گیر کردن
        cmd = f'single-file --browser-executable-path="" "{url}" "{output_path}"'

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            # اعمال تایم‌اوت 60 ثانیه‌ای
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            if process.returncode == 0 and os.path.exists(output_path):
                return True
        except asyncio.TimeoutError:
            process.kill()
            print(f"SingleFile timeout for URL: {url}")
        except Exception as e:
            print(f"SingleFile error: {e}")

        return False
