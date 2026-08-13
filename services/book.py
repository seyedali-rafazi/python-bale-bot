# services/book.py
"""
Multi-source book search & download service.

Sources (in priority order):
  1. Project Gutenberg (via Gutendex API) — classic/public-domain books, direct downloads
  2. Standard Ebooks               — beautifully formatted public-domain EPUBs
  3. Open Library                  — broad catalog; direct OL download where available
  4. DOAB (Directory of Open Access Books) — academic open-access books

No API key required for any source.
All blocking I/O is wrapped in asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
MAX_BOOK_BYTES = 18 * 1024 * 1024   # 18 MB — safe for Bale file sending
_MAX_RETRIES   = 2
_RETRY_DELAY   = 2.0                 # seconds between retries

_TIMEOUT = httpx.Timeout(connect=45.0, read=120.0, write=30.0, pool=10.0)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
}

# Source identifiers
SRC_GUTENBERG = "gutenberg"
SRC_STANDARD  = "standard_ebooks"
SRC_OL        = "open_library"
SRC_DOAB      = "doab"

SOURCE_LABELS = {
    SRC_GUTENBERG: "📗 Project Gutenberg",
    SRC_STANDARD:  "📘 Standard Ebooks",
    SRC_OL:        "📙 Open Library",
    SRC_DOAB:      "🎓 DOAB (Open Access)",
}


def _make_client(verify: bool = True) -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=True,
        verify=verify,
        headers=_HEADERS,
        trust_env=False,
    )


def _get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    retries: int = _MAX_RETRIES,
) -> Optional[httpx.Response]:
    """GET with automatic retry on connection errors."""
    for attempt in range(retries + 1):
        try:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt < retries:
                logger.info("Retry %d/%d for %s: %s", attempt + 1, retries, url, e)
                time.sleep(_RETRY_DELAY)
            else:
                logger.warning("Request failed after %d retries — %s: %s", retries, url, e)
    return None


def _safe_filename(name: str, ext: str = ".epub") -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"\s+", "_", name)
    base = name[:50] or "book"
    if not base.endswith(ext):
        base += ext
    return base


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE 1: Project Gutenberg (Gutendex)
# ──────────────────────────────────────────────────────────────────────────────
_GUTENDEX_URL = "https://gutendex.com/books/"

_PREFER_FORMATS = [
    "application/pdf",
    "application/epub+zip",
    "text/html",
    "text/plain; charset=utf-8",
    "text/plain",
]


def _gutenberg_pick_url(formats: dict) -> tuple[Optional[str], str]:
    """Pick the best download URL and extension from a Gutenberg formats dict."""
    for mime in _PREFER_FORMATS:
        url = formats.get(mime)
        if url and ".images" not in url:   # skip image-heavy variants
            ext = ".pdf" if "pdf" in mime else ".epub" if "epub" in mime else ".html"
            return url, ext
    # Fallback: any epub
    for key, url in formats.items():
        if "epub" in key and url:
            return url, ".epub"
    return None, ".epub"


def _search_gutenberg_sync(query: str, max_results: int) -> List[dict]:
    with _make_client() as client:
        resp = _get_with_retry(
            client, _GUTENDEX_URL,
            params={"search": query, "languages": "en,fa,ar,fr,de,es"},
        )
        if not resp:
            return []
        data = resp.json()

    books = []
    for item in data.get("results", [])[:max_results * 2]:
        formats = item.get("formats", {})
        download_url, ext = _gutenberg_pick_url(formats)
        authors = item.get("authors", [])
        author_str = ", ".join(
            # Gutenberg stores "Lastname, Firstname" — flip it
            " ".join(reversed(a.get("name", "").split(", ", 1)))
            for a in authors
        )[:60] or "نامشخص"
        books.append({
            "title":        (item.get("title") or "نامشخص")[:80],
            "author":       author_str,
            "year":         str(authors[0].get("birth_year", "—")) if authors else "—",
            "source":       SRC_GUTENBERG,
            "source_label": SOURCE_LABELS[SRC_GUTENBERG],
            "has_file":     bool(download_url),
            "download_url": download_url,
            "file_ext":     ext,
            "book_id":      str(item.get("id", "")),
        })
        if len(books) >= max_results:
            break
    return books


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE 2: Standard Ebooks (OPDS 2.0 JSON)
# ──────────────────────────────────────────────────────────────────────────────
_SE_OPDS_URL = "https://standardebooks.org/feeds/opds"
_SE_BASE     = "https://standardebooks.org"


def _search_standard_ebooks_sync(query: str, max_results: int) -> List[dict]:
    """
    Standard Ebooks OPDS 2.0 feed returns the full catalog (no search param).
    We fetch the first page and filter by title/author matching query terms.
    Rate limit: don't hammer this endpoint.
    """
    headers = {**_HEADERS, "Accept": "application/opds+json"}
    with _make_client() as client:
        try:
            resp = client.get(_SE_OPDS_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Standard Ebooks OPDS failed: %s", e)
            return []

    query_words = set(query.lower().split())
    books = []
    for pub in data.get("publications", []):
        title  = (pub.get("title") or "")
        author = ""
        contributors = pub.get("contributors", {})
        if isinstance(contributors, dict):
            authors_list = contributors.get("author", [])
            if isinstance(authors_list, list):
                author = ", ".join(
                    a.get("name", "") for a in authors_list if isinstance(a, dict)
                )
            elif isinstance(authors_list, dict):
                author = authors_list.get("name", "")
        elif isinstance(contributors, list):
            author = ", ".join(
                c.get("name", "") for c in contributors if isinstance(c, dict)
            )

        haystack = (title + " " + author).lower()
        if not any(w in haystack for w in query_words):
            continue

        # Find EPUB acquisition link
        dl_url = None
        for link in pub.get("links", []):
            rel  = link.get("rel", "")
            mime = link.get("type", "")
            href = link.get("href", "")
            if "acquisition" in rel and "epub" in mime and href:
                dl_url = href if href.startswith("http") else _SE_BASE + href
                break

        books.append({
            "title":        title[:80] or "نامشخص",
            "author":       author[:60] or "نامشخص",
            "year":         "—",
            "source":       SRC_STANDARD,
            "source_label": SOURCE_LABELS[SRC_STANDARD],
            "has_file":     bool(dl_url),
            "download_url": dl_url,
            "file_ext":     ".epub",
            "book_id":      pub.get("identifier", ""),
        })
        if len(books) >= max_results:
            break

    return books


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE 3: Open Library
# ──────────────────────────────────────────────────────────────────────────────
_OL_SEARCH = "https://openlibrary.org/search.json"
_OL_BASE   = "https://openlibrary.org"


def _search_openlibrary_sync(query: str, max_results: int) -> List[dict]:
    with _make_client() as client:
        resp = _get_with_retry(
            client, _OL_SEARCH,
            params={
                "q": query,
                "fields": "key,title,author_name,first_publish_year,lending_edition_s,cover_i,ia,public_scan_b,has_fulltext",
                "limit": max_results * 2,
            },
        )
        if not resp:
            return []
        data = resp.json()

    books = []
    for doc in data.get("docs", []):
        raw_ia = doc.get("ia") or []
        ia_list = [item for item in raw_ia if item and isinstance(item, str)]

        # Open Library direct PDF URLs (/books/OL...M.pdf) redirect to verify_human (bot protection HTML page).
        # Direct file downloads are available via Internet Archive identifiers (ia).
        if ia_list:
            dl_url = f"https://archive.org/download/{ia_list[0]}/{ia_list[0]}.pdf"
        else:
            dl_url = None

        books.append({
            "title":        (doc.get("title") or "نامشخص")[:80],
            "author":       ", ".join(doc.get("author_name") or [])[:60] or "نامشخص",
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
# SOURCE 4: DOAB (Directory of Open Access Books)
# ──────────────────────────────────────────────────────────────────────────────
_DOAB_SEARCH = "https://directory.doabooks.org/rest/search"
_DOAB_CHECK  = "https://doab-check.ebookfoundation.org/api/doab/{doab_id}"


def _search_doab_sync(query: str, max_results: int) -> List[dict]:
    with _make_client() as client:
        resp = _get_with_retry(
            client, _DOAB_SEARCH,
            params={
                "query": query,
                "rpp":   max_results * 2,
                "start": 0,
                "expand": "metadata",
            },
        )
        if not resp:
            return []
        items = resp.json()

    books = []
    if not isinstance(items, list):
        return []

    for item in items:
        metadata = item.get("metadata", []) or []

        def _meta(key: str) -> str:
            for m in metadata:
                if m.get("key") == key:
                    return (m.get("value") or "").strip()
            return ""

        title  = _meta("dc.title") or "نامشخص"
        author = _meta("dc.contributor.author") or _meta("dc.creator") or "نامشخص"
        year   = (_meta("dc.date.issued") or "—")[:4]

        # Get DOAB handle for the check API
        handle = _meta("dc.identifier.uri") or ""
        doab_id = item.get("handle", "").replace("20.500.12854/", "") if item.get("handle") else ""

        # Try DOAB-Check API to get a direct PDF link
        dl_url = None
        if doab_id:
            try:
                check_resp = _get_with_retry(
                    client,
                    _DOAB_CHECK.format(doab_id=doab_id),
                    retries=1,
                )
                if check_resp:
                    check_data = check_resp.json()
                    for link in check_data.get("links", []):
                        if link.get("content_type") == "pdf" and link.get("url"):
                            dl_url = link["url"]
                            break
            except Exception as e:
                logger.debug("DOAB-Check failed for %s: %s", doab_id, e)

        books.append({
            "title":        title[:80],
            "author":       author[:60],
            "year":         year,
            "source":       SRC_DOAB,
            "source_label": SOURCE_LABELS[SRC_DOAB],
            "has_file":     bool(dl_url),
            "download_url": dl_url,
            "file_ext":     ".pdf",
            "book_id":      doab_id,
        })
        if len(books) >= max_results:
            break

    return books


# ──────────────────────────────────────────────────────────────────────────────
# Combined search (all sources in parallel)
# ──────────────────────────────────────────────────────────────────────────────
async def search_books(query: str, max_results: int = 8) -> List[dict]:
    """
    Search all four sources concurrently and return a combined, de-duplicated list.
    Books with downloadable files are sorted first.
    """
    per_source = max(4, max_results)

    results = await asyncio.gather(
        asyncio.to_thread(_search_gutenberg_sync,     query, per_source),
        asyncio.to_thread(_search_standard_ebooks_sync, query, per_source),
        asyncio.to_thread(_search_openlibrary_sync,   query, per_source),
        asyncio.to_thread(_search_doab_sync,          query, per_source),
        return_exceptions=True,
    )

    combined: List[dict] = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("Source error during search: %s", res)
            continue
        combined.extend(res)

    # De-duplicate by normalised title
    seen: set[str] = set()
    unique: List[dict] = []
    for book in combined:
        key = re.sub(r"\W+", "", book["title"].lower())[:30]
        if key not in seen:
            seen.add(key)
            unique.append(book)

    # Sort: downloadable first, then by source priority
    source_order = {SRC_GUTENBERG: 0, SRC_STANDARD: 1, SRC_OL: 2, SRC_DOAB: 3}
    unique.sort(key=lambda b: (
        0 if b["has_file"] else 1,
        source_order.get(b["source"], 9),
    ))

    return unique[:max_results]


# ──────────────────────────────────────────────────────────────────────────────
# Download dispatcher
# ──────────────────────────────────────────────────────────────────────────────
def _safe_unlink(path: str) -> None:
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


def _download_url_sync(
    download_url: str,
    dest_path: str,
    *,
    verify: bool = True,
) -> bool:
    """Stream-download *download_url* to *dest_path*. Returns True on success."""
    with _make_client(verify=verify) as client:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with client.stream("GET", download_url) as stream:
                    if stream.status_code != 200:
                        logger.warning("Download URL returned HTTP %d: %s", stream.status_code, download_url)
                        _safe_unlink(dest_path)
                        return False

                    content_type = stream.headers.get("content-type", "").lower()
                    if "text/html" in content_type or "application/xhtml+xml" in content_type:
                        logger.warning("Download URL returned HTML content: %s (type: %s)", download_url, content_type)
                        _safe_unlink(dest_path)
                        return False

                    downloaded = 0
                    first_chunk = True
                    with open(dest_path, "wb") as fh:
                        for chunk in stream.iter_bytes(chunk_size=65536):
                            if first_chunk:
                                first_chunk = False
                                chunk_start = chunk[:512].lower()
                                # Validate HTML / bot protection signature
                                if b"<!doctype" in chunk_start or b"<html" in chunk_start or b"verify_human" in chunk_start:
                                    logger.warning("Downloaded payload is HTML page: %s", download_url)
                                    fh.close()
                                    _safe_unlink(dest_path)
                                    return False

                                # Validate PDF / EPUB magic bytes
                                if dest_path.endswith(".pdf") and b"%PDF-" not in chunk[:1024]:
                                    logger.warning("File missing PDF magic bytes: %s", download_url)
                                    fh.close()
                                    _safe_unlink(dest_path)
                                    return False
                                elif dest_path.endswith(".epub") and b"PK\x03\x04" not in chunk[:128]:
                                    logger.warning("File missing EPUB magic bytes: %s", download_url)
                                    fh.close()
                                    _safe_unlink(dest_path)
                                    return False

                            fh.write(chunk)
                            downloaded += len(chunk)
                            if downloaded > MAX_BOOK_BYTES:
                                logger.warning("File too large (>18 MB): %s", download_url)
                                fh.close()
                                _safe_unlink(dest_path)
                                return False

                if os.path.exists(dest_path) and os.path.getsize(dest_path) >= 10000:
                    return True
                else:
                    logger.warning("Downloaded file too small (<10KB): %s", download_url)
                    _safe_unlink(dest_path)
                    return False
            except Exception as e:
                _safe_unlink(dest_path)
                if attempt < _MAX_RETRIES:
                    logger.info("Download retry %d/%d — %s: %s", attempt + 1, _MAX_RETRIES, download_url, e)
                    time.sleep(_RETRY_DELAY)
                else:
                    logger.warning("Download failed after retries — %s: %s", download_url, e)
    return False


def _download_book_sync(book: dict, dest_dir: str) -> Optional[str]:
    """
    Download the book described by *book* dict to *dest_dir*.
    Returns local file path on success, None otherwise.
    """
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    urls_to_try: List[tuple[str, str]] = []  # (url, file_ext)

    download_url = book.get("download_url")
    ext = book.get("file_ext", ".epub")
    if download_url:
        urls_to_try.append((download_url, ext))

    # For Open Library books with ia_list, add fallback candidate URLs (PDF & EPUB for top ia items)
    ia_list = book.get("ia_list") or []
    if book.get("source") == SRC_OL and ia_list:
        for ia_id in ia_list[:3]:  # Try up to top 3 IA candidates
            pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
            epub_url = f"https://archive.org/download/{ia_id}/{ia_id}.epub"
            if (pdf_url, ".pdf") not in urls_to_try:
                urls_to_try.append((pdf_url, ".pdf"))
            if (epub_url, ".epub") not in urls_to_try:
                urls_to_try.append((epub_url, ".epub"))

    if not urls_to_try:
        logger.info("No download URLs available for book: %s", book.get("title"))
        return None

    verify = book.get("source") != SRC_GUTENBERG

    for url, file_ext in urls_to_try:
        safe_name = _safe_filename(book.get("title", "book"), file_ext)
        dest_path = os.path.join(dest_dir, safe_name)

        success = _download_url_sync(url, dest_path, verify=verify)
        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) >= 10000:
            return dest_path
        _safe_unlink(dest_path)

    return None


async def download_book(book: dict, dest_dir: str) -> Optional[str]:
    """Async wrapper: download a book dict to dest_dir. Returns local path or None."""
    return await asyncio.to_thread(_download_book_sync, book, dest_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────
def format_book_info(book: dict) -> str:
    """Return a compact Markdown summary for one book result."""
    if book["has_file"]:
        icon = "⬇️"
    else:
        icon = "🔒"
    ext_tag = book.get("file_ext", ".epub").lstrip(".").upper()
    return (
        f"{icon} *{book['title']}*\n"
        f"   ✍️ {book['author']} | 📅 {book['year']}\n"
        f"   {book['source_label']} | {ext_tag}"
    )
