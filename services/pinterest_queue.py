# services/pinterest_queue.py

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # برای مخفی کردن اثر انگشت ربات


def search_web(query: str, max_results: int = 10):
    results = []
    # استفاده از بینگ به دلیل پایداری بیشتر در اتوماسیون
    search_url = f"https://www.bing.com/search?q={quote(query)}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # اعمال حالت Stealth برای جلوگیری از شناسایی
            stealth_sync(page)

            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # در بینگ، کلاس b_algo شامل نتایج جستجو است
            # صبر می‌کنیم تا نتایج لود شوند
            page.wait_for_selector(".b_algo", timeout=5000)

            search_results = page.locator(".b_algo").all()

            for result in search_results:
                if len(results) >= max_results:
                    break

                title_el = result.locator("h2 a").first
                if title_el.count() > 0:
                    title = title_el.text_content().strip()
                    url = title_el.get_attribute("href")
                    if url:
                        results.append({"title": title, "url": url})

            browser.close()

    except Exception as e:
        print(f"Search failed: {e}")

    return results


async def queued_pinterest_search(
    query: str,
    max_results: int = 30,
) -> List[str]:
    loop = asyncio.get_running_loop()

    future = loop.create_future()

    await search_queue.put(
        PinterestJob(
            query=query,
            max_results=max_results,
            future=future,
        )
    )

    return await future
