# services/book.py
"""
Book search & download service using the Open Library API.

Search endpoint : https://openlibrary.org/search.json
Download        : Internet Archive (linked from Open Library) for books with
                  lending/freely-available status.

No API key required.  All blocking I/O is wrapped in asyncio.to_thread().
"""

import asyncio
import logging
import os
import re
import urllib.parse
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://openlibrary.org/search.json"
OL_BASE    = "https://openlibrary.org"
IA_DOWNLOAD = "https://archive.org/download/{ia_id}/{ia_id}.pdf"

# Max size we're willing to download and send (18 MB to stay within Bale limit)
MAX_BOOK_BYTES = 18 * 1024 * 1024
REQUEST_TIMEOUT = 30  # seconds


# ──────────────────────────────────────────────────────────────────────────────
# Data class (plain dict is fine for our purposes)
# ──────────────────────────────────────────────────────────────────────────────
def _make_book(raw: dict) -> dict:
    """Normalise a single Open Library search hit into a simple dict."""
    ia_ids: list = raw.get("ia", []) or []
    cover_id = raw.get("cover_i")
    return {
        "title":   (raw.get("title") or "نامشخص")[:80],
        "author":  ", ".join(raw.get("author_name") or [])[:60] or "نامشخص",
        "year":    str(raw.get("first_publish_year") or "—"),
        "ol_key":  raw.get("key", ""),          # e.g. /works/OL123W
        "ia_id":   ia_ids[0] if ia_ids else None,  # Internet Archive identifier
        "has_pdf": bool(ia_ids),
        "cover_id": cover_id,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────────────────
def _search_books_sync(query: str, max_results: int = 8) -> List[dict]:
    params = {
        "q": query,
        "fields": "key,title,author_name,first_publish_year,ia,cover_i",
        "limit": 20,   # fetch more, then filter to those with IA copies
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    docs = data.get("docs", [])
    books = [_make_book(d) for d in docs]

    # Prefer books that have a downloadable copy first
    with_pdf = [b for b in books if b["has_pdf"]]
    without  = [b for b in books if not b["has_pdf"]]
    ordered  = with_pdf + without

    return ordered[:max_results]


async def search_books(query: str, max_results: int = 8) -> List[dict]:
    """Async: search Open Library for books matching *query*."""
    return await asyncio.to_thread(_search_books_sync, query, max_results)


# ──────────────────────────────────────────────────────────────────────────────
# Download
# ──────────────────────────────────────────────────────────────────────────────
def _safe_filename(title: str) -> str:
    """Turn a book title into a safe filename."""
    name = re.sub(r"[^\w\s-]", "", title).strip()
    name = re.sub(r"\s+", "_", name)
    return (name[:50] or "book") + ".pdf"


def _download_book_sync(ia_id: str, dest_dir: str) -> Optional[str]:
    """
    Try to download the PDF from Internet Archive.
    Returns the local file path on success, None if unavailable / too large.
    """
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    # Attempt: direct PDF download
    pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        # HEAD first to check size
        try:
            head = client.head(pdf_url)
            if head.status_code == 200:
                content_length = int(head.headers.get("content-length", 0))
                if content_length > MAX_BOOK_BYTES:
                    logger.warning("Book too large (%d bytes): %s", content_length, ia_id)
                    return None
                download_url = pdf_url
            else:
                # Fall back: query IA metadata to find any PDF/EPUB file
                meta_url = f"https://archive.org/metadata/{ia_id}"
                meta_resp = client.get(meta_url)
                meta_resp.raise_for_status()
                meta = meta_resp.json()
                files = meta.get("files", [])

                # Pick the smallest PDF, then EPUB, then DjVu
                def _sort_key(f):
                    name = f.get("name", "").lower()
                    size = int(f.get("size", 999_999_999))
                    if name.endswith(".pdf"):
                        return (0, size)
                    if name.endswith(".epub"):
                        return (1, size)
                    if name.endswith(".djvu"):
                        return (2, size)
                    return (9, size)

                candidates = [
                    f for f in files
                    if any(f.get("name", "").lower().endswith(ext)
                           for ext in (".pdf", ".epub", ".djvu"))
                    and int(f.get("size", MAX_BOOK_BYTES + 1)) <= MAX_BOOK_BYTES
                ]
                if not candidates:
                    return None
                candidates.sort(key=_sort_key)
                chosen = candidates[0]
                download_url = f"https://archive.org/download/{ia_id}/{urllib.parse.quote(chosen['name'])}"
        except Exception as e:
            logger.warning("IA HEAD/meta failed for %s: %s", ia_id, e)
            return None

        # Stream download
        dest_path = os.path.join(dest_dir, _safe_filename(ia_id))
        try:
            with client.stream("GET", download_url) as stream:
                stream.raise_for_status()
                downloaded = 0
                with open(dest_path, "wb") as fh:
                    for chunk in stream.iter_bytes(chunk_size=65536):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > MAX_BOOK_BYTES:
                            logger.warning("Book exceeded size limit during download: %s", ia_id)
                            fh.close()
                            os.unlink(dest_path)
                            return None
        except Exception as e:
            logger.warning("IA download failed for %s: %s", ia_id, e)
            return None

    return dest_path


async def download_book(ia_id: str, dest_dir: str) -> Optional[str]:
    """Async: download a book by its Internet Archive ID. Returns local path or None."""
    return await asyncio.to_thread(_download_book_sync, ia_id, dest_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def format_book_info(book: dict) -> str:
    """Return a short Markdown summary line for a book."""
    dl_icon = "⬇️" if book["has_pdf"] else "🔒"
    return (
        f"{dl_icon} *{book['title']}*\n"
        f"   ✍️ {book['author']} | 📅 {book['year']}"
    )
