# services/web_scraper.py


import asyncio
import os
from urllib.parse import quote, unquote, parse_qs, urlparse

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from dotenv import load_dotenv

SINGLEFILE_SEMAPHORE = asyncio.Semaphore(5)

load_dotenv()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

PROXY_URL = os.getenv("PROXY")
PLAYWRIGHT_PROXY = {"server": PROXY_URL} if PROXY_URL else None


def clean_google_url(url: str):
    try:
        if not url:
            return None

        # لینک مستقیم
        if url.startswith("http"):
            return url

        # لینک‌های /url?q=
        if url.startswith("/url?"):
            parsed = urlparse(url)
            q = parse_qs(parsed.query)

            real_url = q.get("q", [None])[0]

            if real_url:
                return real_url

    except:
        pass

    return None


def clean_ddg_url(url: str):
    try:
        if not url:
            return None

        # لینک redirect داک‌داک‌گو
        if "duckduckgo.com/l/" in url:
            parsed = urlparse(url)
            q = parse_qs(parsed.query)

            uddg = q.get("uddg", [None])[0]

            if uddg:
                return unquote(uddg)

        return url

    except:
        return url


def search_web(query: str, max_results: int = 10):
    results = []

    search_url = (
        f"https://www.google.com/search?q={quote(query)}&hl=en&num={max_results}"
    )

    try:
        with sync_playwright() as p:
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
                viewport={"width": 1366, "height": 768},
            )

            page = context.new_page()

            page.set_extra_http_headers(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Upgrade-Insecure-Requests": "1",
                }
            )

            print(f"Searching web via Playwright: {search_url} | Proxy: {PROXY_URL}")

            page.goto(
                search_url,
                wait_until="networkidle",
                timeout=45000,
            )

            page.wait_for_timeout(2000)

            # قبول کوکی گوگل
            try:
                accept_btn = page.locator('button:has-text("Accept all")').first

                if accept_btn.count() > 0:
                    accept_btn.click()
                    page.wait_for_timeout(1000)

            except:
                pass

            # سلکتورهای جدید گوگل
            search_results = page.locator("a:has(h3)").all()

            seen = set()

            for item in search_results:
                if len(results) >= max_results:
                    break

                try:
                    h3 = item.locator("h3").first

                    if h3.count() == 0:
                        continue

                    title = h3.text_content()

                    href = item.get_attribute("href")

                    url = clean_google_url(href)

                    if not url:
                        continue

                    if "google.com" in url:
                        continue

                    if url in seen:
                        continue

                    seen.add(url)

                    results.append(
                        {
                            "title": title.strip(),
                            "url": url,
                        }
                    )

                except:
                    continue

            context.close()
            browser.close()

    except PlaywrightTimeoutError:
        print(f"Google Search timeout: {query}")

    except Exception as e:
        print(f"Google Search error: {e}")

    # fallback
    if not results:
        print("Google returned no results, trying DuckDuckGo HTML...")
        results = _fallback_search(query, max_results)

    return results


def _fallback_search(query: str, max_results: int = 10):
    results = []

    search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                proxy=PLAYWRIGHT_PROXY,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            page = browser.new_page(user_agent=USER_AGENT)

            page.goto(
                search_url,
                wait_until="networkidle",
                timeout=45000,
            )

            page.wait_for_timeout(1500)

            items = page.locator(".result").all()

            seen = set()

            for item in items:
                if len(results) >= max_results:
                    break

                try:
                    link = item.locator(".result__title a").first

                    if link.count() == 0:
                        continue

                    title = link.text_content()

                    href = link.get_attribute("href")

                    url = clean_ddg_url(href)

                    if not url:
                        continue

                    if url in seen:
                        continue

                    seen.add(url)

                    results.append(
                        {
                            "title": title.strip(),
                            "url": url,
                        }
                    )

                except:
                    continue

            browser.close()

    except Exception as e:
        print(f"Fallback Search Error: {e}")

    return results
