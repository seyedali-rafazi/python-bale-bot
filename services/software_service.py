# services/software_service.py
"""
Software Service for searching and downloading Android APKs and Windows applications.
High-concurrency optimized:
  - In-memory TTL cache for popular queries to avoid repeated external calls.
  - Subprocess concurrency limiting via Semaphore to protect CPU/RAM.
  - Safe stream downloading with size guards and automatic failed download cleanup.
"""

import asyncio
import hashlib
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from services.cache_service import cache_get, cache_set

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Scoop cloud catalog endpoints (Azure AI Search - cross-platform, works on Linux & Windows)
SCOOP_SEARCH_URL = "https://scoopsearch.search.windows.net/indexes/apps/docs"
SCOOP_API_KEY = "78CB5DCD0A7ABACE5B4DC3C34BC54C8F"

# Limit concurrent winget operations to prevent process storms under heavy load
_WINGET_SEMAPHORE = asyncio.Semaphore(2)

_shared_httpx_client: Optional[httpx.AsyncClient] = None
_httpx_lock = asyncio.Lock()


async def get_software_httpx_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient with connection pooling."""
    global _shared_httpx_client
    if _shared_httpx_client is None or _shared_httpx_client.is_closed:
        async with _httpx_lock:
            if _shared_httpx_client is None or _shared_httpx_client.is_closed:
                _shared_httpx_client = httpx.AsyncClient(
                    headers={"User-Agent": USER_AGENT},
                    timeout=httpx.Timeout(connect=10.0, read=180.0, write=15.0, pool=10.0),
                    limits=httpx.Limits(
                        max_connections=50,
                        max_keepalive_connections=20,
                    ),
                    follow_redirects=True,
                )
    return _shared_httpx_client


async def close_software_httpx_client() -> None:
    global _shared_httpx_client
    async with _httpx_lock:
        if _shared_httpx_client is not None and not _shared_httpx_client.is_closed:
            await _shared_httpx_client.aclose()
            _shared_httpx_client = None

_CACHE_TTL_SECONDS = 1800  # 30 minutes
_MANIFEST_CACHE_TTL_SECONDS = 3600  # 60 minutes

# Max allowed download size (250 MB) to protect bot resources
MAX_ALLOWED_DOWNLOAD_BYTES = 250 * 1024 * 1024

# Common Persian to English software names for better search hit-rate
PERSIAN_NAME_MAP = {
    "تلگرام": "telegram",
    "اینستاگرام": "instagram",
    "واتساپ": "whatsapp",
    "واتس اپ": "whatsapp",
    "گوگل کروم": "chrome",
    "کروم": "chrome",
    "فایرفاکس": "firefox",
    "اسپاتیفای": "spotify",
    "دیسکورد": "discord",
    "اسکایپ": "skype",
    "وی پی ان": "vpn",
    "فیلترشکن": "vpn",
    "شاد": "shad",
    "روبیکا": "rubika",
    "ایتا": "eitaa",
    "بله": "bale",
    "نوت پد": "notepad",
    "وی ال سی": "vlc",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing invalid OS characters."""
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.strip()
    return clean or "software_package"


def _software_cache_key(prefix: str, text: str, limit: int = 0) -> str:
    digest = hashlib.md5(f"{text.lower()}:{limit}".encode("utf-8")).hexdigest()[:16]
    return f"software:{prefix}:{digest}"


class SoftwareService:
    """Service to search and download software for Android and Windows."""

    @classmethod
    def _normalize_query(cls, query: str) -> str:
        q = query.strip().lower()
        return PERSIAN_NAME_MAP.get(q, query.strip())

    @classmethod
    async def search_android(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search Android applications on Aptoide API with in-memory caching.
        Returns a list of dicts with keys:
          name, package, version, size_mb, icon, download_url, updated, platform
        """
        norm_query = cls._normalize_query(query)
        cache_key = _software_cache_key("android", norm_query, limit)

        cached = await cache_get(cache_key)
        if isinstance(cached, list) and cached:
            return cached

        url = "https://ws75.aptoide.com/api/7/apps/search"
        params = {"query": norm_query, "limit": limit}

        try:
            client = await get_software_httpx_client()
            resp = await client.get(url, params=params, timeout=12.0)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("datalist", {}).get("list", [])
            results: List[Dict[str, Any]] = []

            for item in items:
                name = item.get("name") or "نامشخص"
                package = item.get("package") or ""
                file_info = item.get("file", {})
                download_url = file_info.get("path") or file_info.get("path_alt")

                if not download_url:
                    continue

                version = file_info.get("vername") or item.get("vername") or "نامشخص"
                size_bytes = item.get("size") or file_info.get("filesize") or 0
                size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else 0.0
                icon = item.get("icon") or ""
                updated = item.get("updated") or item.get("modified") or "نامشخص"

                results.append(
                    {
                        "name": name,
                        "package": package,
                        "version": version,
                        "size_mb": size_mb,
                        "icon": icon,
                        "download_url": download_url,
                        "updated": updated,
                        "platform": "android",
                        "extension": "apk",
                    }
                )

                if len(results) >= limit:
                    break

            if results:
                await cache_set(cache_key, results, ttl_sec=_CACHE_TTL_SECONDS)
            return results
        except Exception as e:
            logger.exception("Error searching Android software for '%s': %s", query, e)
            return []

    @classmethod
    async def _get_remote_file_size_mb(cls, url: str) -> float:
        """Quickly check Content-Length of a remote URL using HEAD request with strict timeout."""
        try:
            client = await get_software_httpx_client()
            resp = await client.head(url, timeout=3.5)
            if resp.status_code == 200:
                cl = resp.headers.get("content-length")
                if cl and cl.isdigit():
                    return round(int(cl) / (1024 * 1024), 1)
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _extract_scoop_download_url(manifest: dict) -> Optional[str]:
        arch = manifest.get("architecture", {})
        if isinstance(arch, dict):
            for arch_key in ("64bit", "32bit", "arm64"):
                entry = arch.get(arch_key)
                if isinstance(entry, dict) and "url" in entry:
                    u = entry["url"]
                    return u[0] if isinstance(u, list) else u
                elif isinstance(entry, str):
                    return entry

        u = manifest.get("url")
        if u:
            return u[0] if isinstance(u, list) else u
        return None

    @staticmethod
    def _detect_extension(url: str) -> str:
        clean = url.split("#")[0].split("?")[0].lower()
        if ".msi" in clean:
            return "msi"
        elif ".zip" in clean:
            return "zip"
        elif ".7z" in clean:
            return "7z"
        return "exe"

    @classmethod
    async def _search_windows_scoop(cls, norm_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search Windows software via Scoop cloud index (Azure AI Search).
        Fully cross-platform (Linux VPS, Windows, macOS, Docker) without needing local winget CLI.
        """
        headers = {
            "api-key": SCOOP_API_KEY,
            "User-Agent": USER_AGENT,
        }
        params = {
            "api-version": "2020-06-30",
            "search": norm_query,
            "$top": str(limit * 3),
        }

        try:
            client = await get_software_httpx_client()
            resp = await client.get(SCOOP_SEARCH_URL, params=params, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                return []
            data = resp.json()
            docs = data.get("value", [])

            if not docs:
                return []

            candidates = []
            seen_names = set()
            for doc in docs:
                meta = doc.get("Metadata") or {}
                repo = meta.get("Repository", "")
                branch = meta.get("BranchName", "master")
                file_path = meta.get("FilePath", "")
                if not repo or not file_path:
                    continue

                raw_repo = repo.replace("github.com", "raw.githubusercontent.com")
                manifest_url = f"{raw_repo}/{branch}/{file_path}"
                name = doc.get("Name", norm_query)

                name_key = name.lower().strip()
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

                candidates.append({
                    "name": name,
                    "version": doc.get("Version", "نامشخص"),
                    "manifest_url": manifest_url,
                    "stars": meta.get("RepositoryStars", 0),
                    "official": meta.get("OfficialRepository", False),
                })

            candidates.sort(key=lambda c: (c["official"], c["stars"]), reverse=True)

            async def _fetch_manifest(client: httpx.AsyncClient, cand: dict) -> Optional[Dict[str, Any]]:
                m_key = _software_cache_key("scoop_manifest", cand["manifest_url"])
                cached_item = await cache_get(m_key)
                if isinstance(cached_item, dict) and cached_item.get("download_url"):
                    return dict(cached_item)
                try:
                    r = await client.get(cand["manifest_url"], timeout=6.0)
                    if r.status_code == 200:
                        m = r.json()
                        dl_url = cls._extract_scoop_download_url(m)
                        if dl_url:
                            clean_dl = dl_url.split("#")[0]
                            ext = cls._detect_extension(clean_dl)
                            item_data = {
                                "name": cand["name"],
                                "package": cand["name"],
                                "version": cand["version"] or m.get("version", "نامشخص"),
                                "download_url": clean_dl,
                                "extension": ext,
                                "platform": "windows",
                                "size_mb": 0.0,
                                "updated": "نامشخص",
                            }
                            await cache_set(m_key, item_data, ttl_sec=_MANIFEST_CACHE_TTL_SECONDS)
                            return item_data
                except Exception:
                    pass
                return None

            results: List[Dict[str, Any]] = []
            seen_urls = set()
            client = await get_software_httpx_client()
            tasks = [_fetch_manifest(client, c) for c in candidates[: limit + 3]]
            fetched = await asyncio.gather(*tasks, return_exceptions=True)

            valid_items: List[Dict[str, Any]] = []
            for item in fetched:
                if isinstance(item, dict) and item.get("download_url"):
                    dl = item["download_url"]
                    if dl in seen_urls:
                        continue
                    seen_urls.add(dl)
                    valid_items.append(item)
                    if len(valid_items) >= limit:
                        break

            if valid_items:
                sizes = await asyncio.gather(
                    *(cls._get_remote_file_size_mb(it["download_url"]) for it in valid_items),
                    return_exceptions=True,
                )
                for it, sz in zip(valid_items, sizes):
                    it["size_mb"] = sz if isinstance(sz, (int, float)) else 0.0
                    results.append(it)

            return results
        except Exception as e:
            logger.warning("Scoop search failed for '%s': %s", norm_query, e)
            return []

    @classmethod
    async def _winget_show(cls, package_id: str) -> Optional[Dict[str, Any]]:
        """Run `winget show` for a specific package ID under a concurrency semaphore."""
        def _run_show():
            import subprocess
            return subprocess.run(
                ["winget", "show", "--id", package_id, "--source", "winget", "--accept-source-agreements"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=12,
            )

        try:
            async with _WINGET_SEMAPHORE:
                proc = await asyncio.to_thread(_run_show)

            if proc.returncode != 0 or not proc.stdout:
                return None

            stdout = proc.stdout
            url_match = re.search(r"Installer Url:\s*(\S+)", stdout)
            if not url_match:
                return None

            installer_url = url_match.group(1).strip()
            ver_match = re.search(r"Version:\s*(\S+)", stdout)
            version = ver_match.group(1).strip() if ver_match else "نامشخص"

            date_match = re.search(r"Release Date:\s*(\S+)", stdout)
            updated = date_match.group(1).strip() if date_match else "نامشخص"

            ext = cls._detect_extension(installer_url)

            return {
                "download_url": installer_url,
                "version": version,
                "updated": updated,
                "extension": ext,
            }
        except Exception as e:
            logger.debug("winget show failed for %s: %s", package_id, e)
            return None

    @classmethod
    async def _search_windows_winget(cls, norm_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fallback Windows search using local winget CLI (only when winget exists on system)."""
        if not shutil.which("winget"):
            return []

        def _run_search():
            import subprocess
            return subprocess.run(
                ["winget", "search", "--source", "winget", norm_query],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=12,
            )

        try:
            async with _WINGET_SEMAPHORE:
                proc = await asyncio.to_thread(_run_search)

            if proc.returncode != 0 or not proc.stdout:
                return []

            lines = proc.stdout.splitlines()
            if not lines:
                return []

            header = lines[0]
            id_pos = header.find("Id")
            ver_pos = header.find("Version")
            match_pos = header.find("Match")

            if id_pos == -1 or ver_pos == -1:
                return []

            candidates = []
            for line in lines[2:]:
                if not line.strip() or line.startswith("-"):
                    continue
                name = line[:id_pos].strip()
                pkg_id = line[id_pos:ver_pos].strip()
                ver = (
                    line[ver_pos:match_pos].strip()
                    if match_pos != -1
                    else line[ver_pos:].strip()
                )
                if pkg_id and not pkg_id.startswith("Tag:"):
                    candidates.append({"name": name, "id": pkg_id, "version": ver})
                if len(candidates) >= limit + 2:
                    break

            tasks = [cls._winget_show(c["id"]) for c in candidates[: limit + 2]]
            show_results = await asyncio.gather(*tasks, return_exceptions=True)

            results: List[Dict[str, Any]] = []
            valid_candidates: List[tuple[dict, dict]] = []
            for cand, show_res in zip(candidates, show_results):
                if isinstance(show_res, dict) and show_res.get("download_url"):
                    valid_candidates.append((cand, show_res))
                    if len(valid_candidates) >= limit:
                        break

            if valid_candidates:
                sizes = await asyncio.gather(
                    *(cls._get_remote_file_size_mb(sr["download_url"]) for _, sr in valid_candidates),
                    return_exceptions=True,
                )
                for (cand, show_res), sz in zip(valid_candidates, sizes):
                    results.append(
                        {
                            "name": cand["name"],
                            "package": cand["id"],
                            "version": show_res.get("version") or cand["version"] or "نامشخص",
                            "size_mb": sz if isinstance(sz, (int, float)) else 0.0,
                            "download_url": show_res["download_url"],
                            "updated": show_res.get("updated", "نامشخص"),
                            "platform": "windows",
                            "extension": show_res.get("extension", "exe"),
                        }
                    )

            return results
        except Exception as e:
            logger.warning("winget search failed for '%s': %s", norm_query, e)
            return []

    @classmethod
    async def search_windows(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search Windows software with caching and concurrency control.
        Uses universal cloud catalog (cross-platform) with winget CLI fallback when available.
        """
        norm_query = cls._normalize_query(query)
        cache_key = _software_cache_key("windows", norm_query, limit)

        cached = await cache_get(cache_key)
        if isinstance(cached, list) and cached:
            return cached

        # 1. Primary: Cloud catalog search (works on Linux VPS, Docker, Windows)
        results = await cls._search_windows_scoop(norm_query, limit=limit)

        # 2. Fallback: If no results found and local winget CLI is installed
        if not results and shutil.which("winget"):
            results = await cls._search_windows_winget(norm_query, limit=limit)

        if results:
            await cache_set(cache_key, results, ttl_sec=_CACHE_TTL_SECONDS)

        return results

    @classmethod
    async def download_file(
        cls,
        url: str,
        dest_dir: str = "downloads/software",
        filename: Optional[str] = None,
        max_bytes: int = MAX_ALLOWED_DOWNLOAD_BYTES,
    ) -> str:
        """
        Download a file asynchronously with size guard and stream write.
        Cleans up partial files if download fails.
        """
        await asyncio.to_thread(Path(dest_dir).mkdir, parents=True, exist_ok=True)

        if not filename:
            clean_url = url.split("?")[0].split("#")[0]
            inferred = os.path.basename(clean_url)
            filename = sanitize_filename(inferred) or "software_file.bin"
        else:
            filename = sanitize_filename(filename)

        dest_path = os.path.join(dest_dir, filename)

        total_downloaded = 0
        f = None

        try:
            client = await get_software_httpx_client()
            async with client.stream("GET", url, timeout=180.0) as response:
                response.raise_for_status()

                cl_header = response.headers.get("content-length")
                if cl_header and cl_header.isdigit() and int(cl_header) > max_bytes:
                    raise ValueError(f"File size exceeds maximum allowed limit ({max_bytes // (1024 * 1024)} MB).")

                f = await asyncio.to_thread(open, dest_path, "wb")
                async for chunk in response.aiter_bytes(chunk_size=256 * 1024):
                    total_downloaded += len(chunk)
                    if total_downloaded > max_bytes:
                        raise ValueError(f"Downloaded stream exceeded limit ({max_bytes // (1024 * 1024)} MB).")
                    await asyncio.to_thread(f.write, chunk)

            return os.path.abspath(dest_path)
        except Exception:
            if f is not None:
                await asyncio.to_thread(f.close)
                f = None
            # Clean up partial/corrupted file
            if await asyncio.to_thread(os.path.isfile, dest_path):
                try:
                    await asyncio.to_thread(os.remove, dest_path)
                except OSError:
                    pass
            raise
        finally:
            if f is not None:
                await asyncio.to_thread(f.close)
