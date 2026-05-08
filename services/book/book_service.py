# services/book/book_service.py

import io
import asyncio
import aiohttp


async def safe_get_json(session: aiohttp.ClientSession, url: str, timeout: int = 10):
    """
    یک درخواست GET امن برای دریافت JSON با استفاده از aiohttp انجام می‌دهد.
    """
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                print(f"API Error: Status {resp.status} for URL {url}")
                return None
    except Exception as e:
        print(f"Error fetching JSON from {url}: {e}")
        return None


async def search_dbooks(session: aiohttp.ClientSession, query: str):
    """جستجوی غیرهمزمان در dbooks.org."""
    url = f"https://www.dbooks.org/api/search/{query}"
    data = await safe_get_json(session, url)
    books = []
    if data and data.get("status") == "ok":
        for item in data.get("books", []):
            books.append(
                {
                    "source": "dbooks",
                    "id": item.get("id"),
                    "title": item.get("title", "N/A")[:40],
                    "author": item.get("authors", "N/A")[:30],
                    "year": "نامشخص",
                    "ext": ".pdf",
                }
            )
    return books


async def search_gutenberg(session: aiohttp.ClientSession, query: str):
    """جستجوی غیرهمزمان در gutendex.com."""
    url = f"https://gutendex.com/books/?search={query}"
    data = await safe_get_json(session, url)
    books = []
    if data and data.get("results"):
        for item in data.get("results", []):
            formats = item.get("formats", {})
            dl_link, ext = None, ""

            if "application/pdf" in formats:
                dl_link, ext = formats["application/pdf"], ".pdf"
            elif "application/epub+zip" in formats:
                dl_link, ext = formats["application/epub+zip"], ".epub"
            elif "text/plain; charset=us-ascii" in formats:
                dl_link, ext = formats["text/plain; charset=us-ascii"], ".txt"

            if dl_link:
                author_name = "نامشخص"
                if item.get("authors"):
                    author_name = item["authors"][0].get("name", "نامشخص")

                books.append(
                    {
                        "source": "gutenberg",
                        "id": str(item.get("id")),
                        "title": item.get("title", "N/A")[:40],
                        "author": author_name[:30],
                        "year": "نامشخص",
                        "link": dl_link,
                        "ext": ext,
                    }
                )
    return books


async def search_books_by_name(query: str, limit: int = 5):
    """
    جستجوی غیرهمزمان کتاب از طریق APIهای dbooks.org و Gutenberg به صورت موازی.
    """
    async with aiohttp.ClientSession() as session:
        tasks = [search_dbooks(session, query), search_gutenberg(session, query)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_books = []
    if isinstance(results[0], list):
        all_books.extend(results[0])
    else:
        print(f"Error in dbooks search: {results[0]}")

    if isinstance(results[1], list):
        all_books.extend(results[1])
    else:
        print(f"Error in Gutenberg search: {results[1]}")

    return all_books[:limit]


async def download_book_pdf(book_data: dict) -> io.BytesIO | None:
    """
    دانلود غیرهمزمان فایل کتاب بر اساس منبع (dbooks یا Gutenberg).
    """
    source = book_data.get("source")
    download_url = None
    file_ext = book_data.get("ext", ".pdf")

    async with aiohttp.ClientSession() as session:
        try:
            if source == "dbooks":
                book_id = book_data.get("id")
                details_url = f"https://www.dbooks.org/api/book/{book_id}"
                data = await safe_get_json(session, details_url, timeout=15)
                if data and data.get("status") == "ok":
                    download_url = data.get("download")
            elif source == "gutenberg":
                download_url = book_data.get("link")

            if not download_url:
                return None

            async with session.get(download_url, timeout=90) as file_resp:
                if file_resp.status == 200:
                    content_length = file_resp.headers.get("Content-Length")
                    if content_length and int(content_length) > 50 * 1024 * 1024:
                        print("File size exceeds 50MB limit.")
                        return None

                    file_content = await file_resp.read()
                    file_stream = io.BytesIO(file_content)
                    safe_title = "".join(
                        x
                        for x in book_data.get("title", "book")
                        if x.isalnum() or x in " _-"
                    )
                    file_stream.name = f"{safe_title[:30]}{file_ext}"
                    return file_stream
                else:
                    return None
        except Exception as e:
            print(f"An unexpected error occurred during download: {e}")
            return None
