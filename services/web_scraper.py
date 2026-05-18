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
        # اصلاح نحوه پاس دادن آرگومان‌ها برای subprocess
        command = [
            "single-file",
            "--browser-args",
            '["--no-sandbox", "--disable-setuid-sandbox"]',
            "--remove-hidden-elements",
            # اگر ورژن single-file شما این فلگ را نمیشناسد، خط زیر را کامنت/حذف کنید
            "--remove-fixed-elements",
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
                # خواندن هر دو خروجی برای پیدا کردن دلیل اصلی ارور
                out_msg = stdout.decode().strip() if stdout else ""
                err_msg = stderr.decode().strip() if stderr else ""

                error_details = (
                    err_msg if err_msg else (out_msg if out_msg else "بدون پیام خطا")
                )
                print(
                    f"SingleFile failed. Code: {process.returncode}. Details: {error_details}"
                )

        except asyncio.TimeoutError:
            process.kill()
            print(f"SingleFile timeout for URL: {url}")
        except Exception as e:
            print(f"SingleFile error: {e}")

        return False
