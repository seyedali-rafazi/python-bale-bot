# services/web_scraper.py

import asyncio
import os
import time
from ddgs import (
    DDGS,
)  # در صورت خطا در ایمپورت، این خط جایگزین from ddgs شد

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
    """اجرای غیرهمزمان ابزار SingleFile CLI با هندل کردن پاپ‌آپ‌ها"""
    async with SINGLEFILE_SEMAPHORE:
        # استفاده از آرگومان‌های مرورگر برای مسدود کردن دامنه‌های معروف کوکی و پاپ‌آپ
        # همچنین مخفی کردن عناصر ثابت (fixed) که معمولاً پاپ‌آپ‌های کوکی هستند
        command = [
            "single-file",
            '--browser-args=["--no-sandbox", "--disable-setuid-sandbox"]',
            "--remove-hidden-elements=true",
            "--remove-fixed-elements=true",  # حذف عناصر ثابت (مثل پاپ‌آپ کوکی و هدرهای مزاحم)
            "--block-scripts=false",
            url,
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            # اعمال تایم‌اوت 60 ثانیه‌ای
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            if process.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                err_msg = stderr.decode() if stderr else "Unknown Error"
                print(f"SingleFile failed. Error: {err_msg}")

        except asyncio.TimeoutError:
            process.kill()
            print(f"SingleFile timeout for URL: {url}")
        except Exception as e:
            print(f"SingleFile error: {e}")

        return False
