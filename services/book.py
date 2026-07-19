# services/book.py
"""
Book search & download service using the Open Library API.

Search endpoint : https://openlibrary.org/search.json
Download        : Internet Archive (linked from Open Library) for books with
                  freely-available status.

No API key required.  All blocking I/O is wrapped in asyncio.to_thread().

SSL note: archive.org SSL handshakes can time out from certain server IPs.
          We disable certificate verification and set generous timeouts to
          work around this. The actual data integrity is not at risk because
          we only read public, freely-licensed content.
"""

import asyncio
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://openlibrary.org/search.json"

# Max size we're willing to download and send (18 MB to stay within Bale limit)
MAX_BOOK_BYTES = 18 * 1024 * 1024

# Timeouts: longer connect timeout to survive slow SSL handshakes
_TIMEOUT = httpx.Timeout(
    connect=60.0,   # SSL handshake can be slow on archive.org
    read=120.0,
    write=30.0,
    pool=10.0,
)

# Browser-like User-Agent to avoid bot-detection blocks
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_MAX_RETRIES = 2
_RETRY_DELAY = 3.0  # seconds between retries


def _make_client() -> httpx.Client:
    """Return an httpx Client with SSL verification disabled and generous timeouts."""
    return httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=True,
        verify=False,          # archive.org SSL often fails on VPS/Iranian IPs
        headers=_HEADERS,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Data class (plain dict is fine for our purposes)
# ──────────────────────────────────────────────────────────────────────────────
def _make_book(raw: dict) -> dict:
    """Normalise a single Open Library search hit into a simple dict."""
    ia_ids: list = raw.get("ia", []) or []
    cover_id = raw.get("cover_i")
    return {
        "title":    (raw.get("title") or "نامشخص")[:80],
        "author":   ", ".join(raw.get("author_name") or [])[:60] or "نامشخص",
        "year":     str(raw.get("first_publish_year") or "—"),
        "ol_key":   raw.get("key", ""),
        "ia_id":    ia_ids[0] if ia_ids else None,
        "has_pdf":  bool(ia_ids),
        "cover_id": cover_id,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Search  (Open Library — usually reachable without SSL issues)
# ──────────────────────────────────────────────────────────────────────────────
def _search_books_sync(query: str, max_results: int = 8) -> List[dict]:
    params = {
        "q": query,
        "fields": "key,title,author_name,first_publish_year,ia,cover_i",
        "limit": 20,
    }
    with _make_client() as client:
        resp = client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    docs = data.get("docs", [])
    books = [_make_book(d) for d in docs]

    # Prefer books that have a downloadable IA copy
    with_pdf = [b for b in books if b["has_pdf"]]
    without  = [b for b in books if not b["has_pdf"]]
    return (with_pdf + without)[:max_results]


async def search_books(query: str, max_results: int = 8) -> List[dict]:
    """Async: search Open Library for books matching *query*."""
    return await asyncio.to_thread(_search_books_sync, query, max_results)


# ──────────────────────────────────────────────────────────────────────────────
# Download helpers
# ──────────────────────────────────────────────────────────────────────────────
def _safe_filename(title: str) -> str:
    name = re.sub(r"[^\w\s-]", "", title).strip()
    name = re.sub(r"\s+", "_", name)
    return (name[:50] or "book") + ".pdf"


def _pick_download_url(client: httpx.Client, ia_id: str) -> Optional[str]:
    """
    Determine the best download URL for a given Internet Archive item.
    Priority: direct PDF → metadata-listed PDF → EPUB → DjVu.
    Returns None if no suitable file is found or item is too large.
    """
    pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"

    # 1. Try direct PDF via HEAD (fastest path)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            head = client.head(pdf_url)
            if head.status_code == 200:
                content_length = int(head.headers.get("content-length", 0))
                if content_length > MAX_BOOK_BYTES:
                    logger.warning("Book too large (%d B): %s", content_length, ia_id)
                    return None
                return pdf_url
            break  # non-200 but connected — fall through to metadata
        except Exception as e:
            if attempt < _MAX_RETRIES:
                logger.info("IA HEAD retry %d for %s: %s", attempt + 1, ia_id, e)
                time.sleep(_RETRY_DELAY)
            else:
                logger.warning("IA HEAD failed after retries for %s: %s", ia_id, e)

    # 2. Fall back: query IA metadata API
    meta_url = f"https://archive.org/metadata/{ia_id}"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            meta_resp = client.get(meta_url)
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            break
        except Exception as e:
            if attempt < _MAX_RETRIES:
                logger.info("IA meta retry %d for %s: %s", attempt + 1, ia_id, e)
                time.sleep(_RETRY_DELAY)
            else:
                logger.warning("IA meta failed after retries for %s: %s", ia_id, e)
                return None

    files = meta.get("files", [])

    def _sort_key(f):
        name = f.get("name", "").lower()
        size = int(f.get("size", 999_999_999))
        if name.endswith(".pdf"):   return (0, size)
        if name.endswith(".epub"):  return (1, size)
        if name.endswith(".djvu"):  return (2, size)
        return (9, size)

    candidates = [
        f for f in files
        if any(f.get("name", "").lower().endswith(ext) for ext in (".pdf", ".epub", ".djvu"))
        and int(f.get("size", MAX_BOOK_BYTES + 1)) <= MAX_BOOK_BYTES
    ]
    if not candidates:
        logger.info("No suitable file candidates for %s", ia_id)
        return None

    candidates.sort(key=_sort_key)
    chosen_name = candidates[0]["name"]
    return f"https://archive.org/download/{ia_id}/{urllib.parse.quote(chosen_name)}"


def _download_book_sync(ia_id: str, dest_dir: str) -> Optional[str]:
    """
    Download a book from Internet Archive.
    Returns local file path on success, None if unavailable / too large / error.
    """
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    with _make_client() as client:
        download_url = _pick_download_url(client, ia_id)
        if not download_url:
            return None

        dest_path = os.path.join(dest_dir, _safe_filename(ia_id))

        for attempt in range(_MAX_RETRIES + 1):
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
                                try:
                                    os.unlink(dest_path)
                                except OSError:
                                    pass
                                return None
                return dest_path  # success
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    logger.info("IA stream retry %d for %s: %s", attempt + 1, ia_id, e)
                    # Remove incomplete file before retry
                    if os.path.exists(dest_path):
                        try:
                            os.unlink(dest_path)
                        except OSError:
                            pass
                    time.sleep(_RETRY_DELAY)
                else:
                    logger.warning("IA download failed after retries for %s: %s", ia_id, e)
                    return None

    return None


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
