# services/book.py

import aiohttp
import asyncio
import uuid


async def fetch_dbooks(session, query):
    try:
        async with session.get(
            f"https://www.dbooks.org/api/search/{query}", timeout=10
        ) as resp:
            data = await resp.json()
            if data.get("status") == "ok":
                return [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "author": item.get("authors"),
                        "source": "dBooks.org",
                        "has_pdf": True,
                        "pdf_url": "needs_fetch",
                    }
                    for item in data.get("books", [])[:3]
                ]
    except Exception as e:
        print(f"DBooks error: {e}")
    return []


async def fetch_gutenberg(session, query):
    try:
        async with session.get(
            f"https://gutendex.com/books?search={query}", timeout=10
        ) as resp:
            data = await resp.json()
            return [
                {
                    "id": str(item["id"]),
                    "title": item.get("title"),
                    "author": ", ".join(
                        [a.get("name", "Unknown") for a in item.get("authors", [])]
                    ),
                    "source": "Project Gutenberg",
                    "has_pdf": bool(item.get("formats", {}).get("application/pdf")),
                    "pdf_url": item.get("formats", {}).get("application/pdf"),
                }
                for item in data.get("results", [])[:3]
            ]
    except Exception as e:
        print(f"Gutenberg error: {e}")
    return []


async def search_books(query):
    async with aiohttp.ClientSession() as session:
        # اجرای همزمان هر دو جستجو
        dbooks_task = fetch_dbooks(session, query)
        gutenberg_task = fetch_gutenberg(session, query)

        results = await asyncio.gather(dbooks_task, gutenberg_task)
        # ترکیب نتایج دو جستجو
        return results[0] + results[1]


async def get_dbooks_download_url(book_id):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.dbooks.org/api/book/{book_id}", timeout=10
            ) as resp:
                data = await resp.json()
                return data.get("download")
    except:
        return None


async def download_pdf(url):
    try:
        # ایجاد نام یکتا برای جلوگیری از تداخل دانلود همزمان کاربران
        file_path = f"tmp_{uuid.uuid4().hex}.pdf"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
        return file_path
    except Exception as e:
        print(f"PDF Download error: {e}")
        return None
