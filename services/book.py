# services/book.py
"""
Multi-source book search & download service.

Sources (in priority order):
  1. Internet Archive (Archive.org)  — vast library of technical, academic, and public-domain books (direct PDF)
  2. Project Gutenberg               — classic literature & public-domain EPUBs (direct download)
  3. Open Library                    — comprehensive global catalog & metadata

No API key required for any source.
Uses native async httpx.AsyncClient connection pooling so no ThreadPoolExecutor slots are blocked.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
import zipfile
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
MAX_BOOK_BYTES = 50 * 1024 * 1024   # 50 MB — Bale file sending limit
_MAX_RETRIES   = 1
_RETRY_DELAY   = 1.0                 # seconds between retries
_SEARCH_DEADLINE = 20.0              # max seconds to wait for search sources

_TIMEOUT = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=10.0)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}

# Source identifiers
SRC_IA        = "archive_org"
SRC_GUTENBERG = "gutenberg"
SRC_OL        = "open_library"
SRC_STANDARD  = "standard_ebooks"
SRC_DOAB      = "doab"

SOURCE_LABELS = {
    SRC_IA:        "🏛 Internet Archive",
    SRC_GUTENBERG: "📗 Project Gutenberg",
    SRC_OL:        "📙 Open Library",
    SRC_STANDARD:  "📘 Standard Ebooks",
    SRC_DOAB:      "🎓 DOAB (Open Access)",
}

_async_clients: dict[bool, httpx.AsyncClient] = {}
_async_clients_lock = asyncio.Lock()
_BOOK_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(4)


async def _get_shared_async_client(verify: bool = True) -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    client = _async_clients.get(verify)
    if client is not None and not client.is_closed:
        return client

    async with _async_clients_lock:
        client = _async_clients.get(verify)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=True,
                verify=verify,
                headers=_HEADERS,
                trust_env=False,
                limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
            )
            _async_clients[verify] = client
        return client


async def close_book_clients() -> None:
    async with _async_clients_lock:
        for client in _async_clients.values():
            if not client.is_closed:
                try:
                    await client.aclose()
                except Exception:
                    pass
        _async_clients.clear()


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    retries: int = _MAX_RETRIES,
) -> Optional[httpx.Response]:
    """Async GET with automatic retry on connection errors."""
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if attempt < retries:
                logger.info("Retry %d/%d for %s: %s", attempt + 1, retries, url, e)
                await asyncio.sleep(_RETRY_DELAY)
            else:
                logger.warning("Request failed after %d retries — %s: %s", retries, url, e)
    return None


def _safe_filename(name: str, ext: str = ".pdf") -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"\s+", "_", name)
    base = name[:50] or "book"
    if not base.endswith(ext):
        base += ext
    return base


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE 1: Internet Archive (Advanced Search & Metadata Files)
# ──────────────────────────────────────────────────────────────────────────────
_IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
_IA_META_URL   = "https://archive.org/metadata/{ident}/files"


async def _search_internet_archive(query: str, max_results: int) -> List[dict]:
    """Search Internet Archive for public/downloadable texts in PDF format."""
    clean_query = query.replace('"', '').strip()
    params = {
        "q": f"({clean_query}) AND mediatype:texts AND format:pdf",
        "fl[]": ["identifier", "title", "creator", "year", "downloads"],
        "sort[]": "downloads desc",
        "rows": max(max_results * 2, 6),
        "page": 1,
        "output": "json",
    }

    client = await _get_shared_async_client()
    try:
        resp = await _get_with_retry(client, _IA_SEARCH_URL, params=params, retries=1)
        if not resp:
            return []
        docs = resp.json().get("response", {}).get("docs", [])
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Internet Archive search failed: %s", e)
        return []

    if not docs:
        return []

    meta_sem = asyncio.Semaphore(6)

    async def _resolve_pdf(doc: dict) -> Optional[dict]:
        ident = doc.get("identifier")
        if not ident:
            return None
        try:
            async with meta_sem:
                meta_resp = await client.get(_IA_META_URL.format(ident=ident), timeout=6.0)
            if meta_resp.status_code != 200:
                return None
            files = meta_resp.json().get("result", [])
            best_pdf = None
            best_size = 0
            for f in files:
                name = f.get("name", "")
                size = int(f.get("size", 0) or 0)
                if name.lower().endswith(".pdf") and 50000 < size < MAX_BOOK_BYTES:
                    if not best_pdf or (size > best_size and not name.endswith("_text.pdf")):
                        best_pdf = name
                        best_size = size

            if best_pdf:
                creator = doc.get("creator")
                if isinstance(creator, list):
                    creator = ", ".join(creator)
                dl_url = f"https://archive.org/download/{ident}/{urllib.parse.quote(best_pdf)}"
                return {
                    "title":        (doc.get("title") or ident)[:80],
                    "author":       (creator or "نامشخص")[:60],
                    "year":         str(doc.get("year") or "—"),
                    "source":       SRC_IA,
                    "source_label": SOURCE_LABELS[SRC_IA],
                    "has_file":     True,
                    "download_url": dl_url,
                    "file_ext":     ".pdf",
                    "book_id":      ident,
                }
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        return None

    resolved = await asyncio.gather(
        *(_resolve_pdf(doc) for doc in docs),
        return_exceptions=True,
    )
    books: List[dict] = []
    for item in resolved:
        if isinstance(item, dict):
            books.append(item)
            if len(books) >= max_results:
                break
    return books


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE 2: Project Gutenberg (Direct Web Search & EPUBs)
# ──────────────────────────────────────────────────────────────────────────────
_GUTENBERG_SEARCH_URL = "https://www.gutenberg.org/ebooks/search/"
_GUTENBERG_PATTERN = re.compile(
    r'<li class="booklink">.*?href="/ebooks/(\d+)".*?'
    r'<span class="title">(.*?)</span>.*?'
    r'<span class="subtitle">(.*?)</span>',
    re.DOTALL,
)


async def _search_gutenberg(query: str, max_results: int) -> List[dict]:
    """Search Gutenberg directly on www.gutenberg.org without Cloudflare blocks."""
    url = f"{_GUTENBERG_SEARCH_URL}?query={urllib.parse.quote_plus(query)}"
    books: List[dict] = []
    client = await _get_shared_async_client()
    try:
        resp = await _get_with_retry(client, url, retries=1)
        if not resp:
            return []
        items = _GUTENBERG_PATTERN.findall(resp.text)
        for book_id, raw_title, raw_author in items[:max_results]:
            title = re.sub(r"<.*?>", "", raw_title).strip()
            author = re.sub(r"<.*?>", "", raw_author).strip()
            books.append({
                "title":        title[:80] or "نامشخص",
                "author":       author[:60] or "نامشخص",
                "year":         "—",
                "source":       SRC_GUTENBERG,
                "source_label": SOURCE_LABELS[SRC_GUTENBERG],
                "has_file":     True,
                "download_url": f"https://www.gutenberg.org/ebooks/{book_id}.epub3.images",
                "fallback_urls": [
                    f"https://www.gutenberg.org/ebooks/{book_id}.epub.noimages",
                    f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.epub",
                ],
                "file_ext":     ".epub",
                "book_id":      book_id,
            })
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Gutenberg search error: %s", e)
    return books


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE 3: Open Library
# ──────────────────────────────────────────────────────────────────────────────
_OL_SEARCH = "https://openlibrary.org/search.json"


async def _search_openlibrary(query: str, max_results: int) -> List[dict]:
    """Lightweight search on Open Library for book catalog metadata."""
    client = await _get_shared_async_client()
    resp = await _get_with_retry(
        client,
        _OL_SEARCH,
        params={
            "q": query,
            "fields": "key,title,author_name,first_publish_year,ia",
            "limit": max_results,
        },
        retries=1,
    )
    if not resp:
        return []
    try:
        data = resp.json()
    except Exception:
        return []

    books: List[dict] = []
    for doc in data.get("docs", []):
        raw_ia = doc.get("ia") or []
        ia_list = [item for item in raw_ia if item and isinstance(item, str)]
        dl_url = None
        if ia_list:
            dl_url = f"https://archive.org/download/{ia_list[0]}/{ia_list[0]}.pdf"

        authors = doc.get("author_name") or []
        books.append({
            "title":        (doc.get("title") or "نامشخص")[:80],
            "author":       ", ".join(authors)[:60] or "نامشخص",
            "year":         str(doc.get("first_publish_year") or "—"),
            "source":       SRC_OL,
            "source_label": SOURCE_LABELS[SRC_OL],
            "has_file":     bool(dl_url),
            "download_url": dl_url,
            "ia_list":      ia_list,
            "file_ext":     ".pdf",
            "book_id":      doc.get("key", ""),
        })
        if len(books) >= max_results:
            break

    return books


# ──────────────────────────────────────────────────────────────────────────────
# Combined search (all sources in parallel)
# ──────────────────────────────────────────────────────────────────────────────
async def search_books(query: str, max_results: int = 8) -> List[dict]:
    """
    Search sources concurrently and return a combined, de-duplicated list.
    Books with downloadable files are sorted first.
    """
    per_source = max(4, max_results // 2 + 1)

    tasks = [
        asyncio.create_task(_search_internet_archive(query, per_source)),
        asyncio.create_task(_search_gutenberg(query, per_source)),
        asyncio.create_task(_search_openlibrary(query, per_source)),
    ]

    done, pending = await asyncio.wait(tasks, timeout=_SEARCH_DEADLINE)
    for t in pending:
        t.cancel()
        logger.warning("A book source timed out during search")
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    combined: List[dict] = []
    for t in done:
        try:
            combined.extend(t.result())
        except Exception as e:
            logger.warning("Source error during search: %s", e)

    # De-duplicate by normalised title
    seen: set[str] = set()
    unique: List[dict] = []
    for book in combined:
        key = re.sub(r"\W+", "", book["title"].lower())[:30]
        if key not in seen:
            seen.add(key)
            unique.append(book)

    # Sort: downloadable first, then by source priority (IA > Gutenberg > OL)
    source_order = {SRC_IA: 0, SRC_GUTENBERG: 1, SRC_OL: 2}
    unique.sort(key=lambda b: (
        0 if b["has_file"] else 1,
        source_order.get(b["source"], 9),
    ))

    return unique[:max_results]


# ──────────────────────────────────────────────────────────────────────────────
# Download dispatcher
# ──────────────────────────────────────────────────────────────────────────────
def _is_valid_file(path: str) -> bool:
    """Check the finished file is complete (not truncated / corrupt)."""
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        return False
    try:
        if path.endswith(".pdf"):
            with open(path, "rb") as fh:
                fh.seek(-2048, os.SEEK_END)
                return b"%%EOF" in fh.read()
        if path.endswith(".epub"):
            with zipfile.ZipFile(path) as z:
                return z.testzip() is None and "META-INF/container.xml" in z.namelist()
    except Exception:
        return False
    return True


def _safe_unlink(path: str) -> None:
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


async def _download_url_async(
    download_url: str,
    dest_path: str,
    *,
    verify: bool = True,
) -> bool:
    """Stream-download *download_url* to *dest_path*. Returns True on success."""
    client = await _get_shared_async_client(verify=verify)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with client.stream("GET", download_url) as stream:
                if stream.status_code != 200:
                    logger.info("Download URL returned HTTP %d: %s", stream.status_code, download_url)
                    _safe_unlink(dest_path)
                    return False

                content_type = stream.headers.get("content-type", "").lower()
                if "text/html" in content_type or "application/xhtml+xml" in content_type:
                    logger.warning("Download URL returned HTML content: %s", download_url)
                    _safe_unlink(dest_path)
                    return False

                cl_header = stream.headers.get("content-length")
                if cl_header and cl_header.isdigit() and int(cl_header) > MAX_BOOK_BYTES:
                    logger.warning("File too large via Content-Length (>50 MB): %s", download_url)
                    _safe_unlink(dest_path)
                    return False

                downloaded = 0
                first_chunk = True
                write_buf = bytearray()
                write_threshold = 512 * 1024
                fh = await asyncio.to_thread(open, dest_path, "wb")
                try:
                    async for chunk in stream.aiter_bytes(chunk_size=131072):
                        if first_chunk:
                            first_chunk = False
                            chunk_start = chunk[:512].lower()
                            if b"<!doctype" in chunk_start or b"<html" in chunk_start or b"verify_human" in chunk_start:
                                logger.warning("Downloaded payload is HTML page: %s", download_url)
                                await asyncio.to_thread(fh.close)
                                fh = None
                                await asyncio.to_thread(_safe_unlink, dest_path)
                                return False

                            if dest_path.endswith(".pdf") and b"%PDF-" not in chunk[:1024]:
                                logger.warning("File missing PDF magic bytes: %s", download_url)
                                await asyncio.to_thread(fh.close)
                                fh = None
                                await asyncio.to_thread(_safe_unlink, dest_path)
                                return False
                            elif dest_path.endswith(".epub") and b"PK\x03\x04" not in chunk[:128]:
                                logger.warning("File missing EPUB magic bytes: %s", download_url)
                                await asyncio.to_thread(fh.close)
                                fh = None
                                await asyncio.to_thread(_safe_unlink, dest_path)
                                return False

                        downloaded += len(chunk)
                        if downloaded > MAX_BOOK_BYTES:
                            logger.warning("File too large (>50 MB): %s", download_url)
                            await asyncio.to_thread(fh.close)
                            fh = None
                            await asyncio.to_thread(_safe_unlink, dest_path)
                            return False
                        write_buf.extend(chunk)
                        if len(write_buf) >= write_threshold:
                            payload = bytes(write_buf)
                            write_buf.clear()
                            await asyncio.to_thread(fh.write, payload)
                    if write_buf:
                        payload = bytes(write_buf)
                        write_buf.clear()
                        await asyncio.to_thread(fh.write, payload)
                finally:
                    if fh is not None:
                        await asyncio.to_thread(fh.close)

            if await asyncio.to_thread(_is_valid_file, dest_path):
                return True
            logger.warning("Downloaded file invalid/corrupt: %s", download_url)
            _safe_unlink(dest_path)
            return False
        except asyncio.CancelledError:
            _safe_unlink(dest_path)
            raise
        except Exception as e:
            _safe_unlink(dest_path)
            if attempt < _MAX_RETRIES:
                logger.info("Download retry %d/%d — %s: %s", attempt + 1, _MAX_RETRIES, download_url, e)
                await asyncio.sleep(_RETRY_DELAY)
            else:
                logger.warning("Download failed after retries — %s: %s", download_url, e)
    return False


async def download_book(book: dict, dest_dir: str) -> Optional[str]:
    """Download a book dict to dest_dir asynchronously. Returns local path or None."""
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    urls_to_try: List[tuple[str, str]] = []  # (url, file_ext)

    download_url = book.get("download_url")
    ext = book.get("file_ext", ".pdf")
    if download_url:
        urls_to_try.append((download_url, ext))

    for fallback in book.get("fallback_urls", []):
        if (fallback, ext) not in urls_to_try:
            urls_to_try.append((fallback, ext))

    ia_list = book.get("ia_list") or []
    if book.get("source") == SRC_OL and ia_list:
        for ia_id in ia_list[:2]:
            pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
            if (pdf_url, ".pdf") not in urls_to_try:
                urls_to_try.append((pdf_url, ".pdf"))

    if not urls_to_try:
        logger.info("No download URLs available for book: %s", book.get("title"))
        return None

    async with _BOOK_DOWNLOAD_SEMAPHORE:
        for url, file_ext in urls_to_try:
            safe_name = _safe_filename(book.get("title", "book"), file_ext)
            dest_path = os.path.join(dest_dir, safe_name)

            success = await _download_url_async(url, dest_path)
            if success and os.path.exists(dest_path) and os.path.getsize(dest_path) >= 10000:
                return dest_path
            _safe_unlink(dest_path)

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────
def format_book_info(book: dict) -> str:
    """Return a compact Markdown summary for one book result."""
    icon = "⬇️" if book["has_file"] else "🔒"
    ext_tag = book.get("file_ext", ".pdf").lstrip(".").upper()
    return (
        f"{icon} *{book['title']}*\n"
        f"   ✍️ {book['author']} | 📅 {book['year']}\n"
        f"   {book['source_label']} | {ext_tag}"
    )
