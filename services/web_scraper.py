# services/web_scraper.py

import asyncio
import os
import time
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv


# محدودکننده برای جلوگیری از هنگ کردن سرور هنگام رندر همزمان صفحات سنگین
SINGLEFILE_SEMAPHORE = asyncio.Semaphore(5)
load_dotenv()


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# دریافت پروکسی از متغیر محیطی (مانند کد اینستاگرام شما)
PROXY_URL = os.getenv("PROXY")
PLAYWRIGHT_PROXY = {"server": PROXY_URL} if PROXY_URL else None


def search_web(query: str, max_results: int = 10):
    """جستجو در وب با استفاده از Playwright و موتور جستجوی گوگل"""
    results = []
    search_url = f"https://www.google.com/search?q={quote(query)}&hl=en"

    try:
        with sync_playwright() as p:
            # اعمال پروکسی در اینجا
            browser = p.chromium.launch(
                headless=True,
                proxy=PLAYWRIGHT_PROXY,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )

            page = context.new_page()

            # تنظیم هدرها برای شبیه‌سازی کاربر واقعی
            page.set_extra_http_headers(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )

            print(f"Searching web via Playwright: {search_url} | Proxy: {PROXY_URL}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # اسکرول کوتاه برای لود شدن کامل نتایج
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(1000)

            # استخراج نتایج جستجوی گوگل
            search_results = page.locator("div.g").all()

            for result in search_results:
                if len(results) >= max_results:
                    break

                try:
                    title_element = result.locator("h3").first
                    link_element = result.locator("a").first

                    if title_element.count() > 0 and link_element.count() > 0:
                        title = title_element.text_content().strip()
                        url = link_element.get_attribute("href")

                        # فیلتر کردن لینک‌های نامعتبر
                        if url and url.startswith("http") and not "google.com" in url:
                            results.append({"title": title, "url": url})
                except Exception as e:
                    continue

            context.close()
            browser.close()

    except PlaywrightTimeoutError:
        print(f"Web Search Playwright timeout for query={query}")
    except Exception as e:
        print(f"Web Search Playwright error: {e}")

    # اگر گوگل به خاطر ریکوئست‌ها بلاک کرد و نتیجه‌ای برنگشت
    if not results:
        print("Google returned no results, trying DuckDuckGo HTML...")
        results = _fallback_search(query, max_results)

    return results


def _fallback_search(query: str, max_results: int = 10):
    """جستجوی جایگزین در نسخه HTML داک‌داک‌گو در صورت مسدود شدن توسط گوگل"""
    results = []
    search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

    try:
        with sync_playwright() as p:
            # اعمال پروکسی در فال‌بک
            browser = p.chromium.launch(
                headless=True,
                proxy=PLAYWRIGHT_PROXY,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            search_results = page.locator(".result__body").all()
            for result in search_results:
                if len(results) >= max_results:
                    break
                try:
                    title_el = result.locator(".result__title a").first
                    if title_el.count() > 0:
                        title = title_el.text_content().strip()
                        url = title_el.get_attribute("href")
                        if url and url.startswith("//duckduckgo.com"):
                            url = "https:" + url
                        results.append({"title": title, "url": url})
                except:
                    continue
            browser.close()
    except Exception as e:
        print(f"Fallback Search Error: {e}")

    return results


async def create_single_file(url, output_path):
    """اجرای غیرهمزمان ابزار SingleFile CLI"""
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
