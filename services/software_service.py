# services/software_service.py
"""
Software Service for searching and downloading Android APKs and Windows applications.
Sources:
  - Android: Aptoide API (https://ws75.aptoide.com/api/7/apps/search)
  - Windows: Windows Package Manager (winget CLI)
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

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


class SoftwareService:
    """Service to search and download software for Android and Windows."""

    @classmethod
    def _normalize_query(cls, query: str) -> str:
        q = query.strip().lower()
        return PERSIAN_NAME_MAP.get(q, query.strip())

    @classmethod
    async def search_android(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search Android applications on Aptoide API.
        Returns a list of dicts with keys:
          name, package, version, size_mb, icon, download_url, updated, platform
        """
        norm_query = cls._normalize_query(query)
        url = "https://ws75.aptoide.com/api/7/apps/search"
        headers = {"User-Agent": USER_AGENT}
        params = {"query": norm_query, "limit": limit}

        try:
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, params=params)
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

            return results
        except Exception as e:
            logger.exception("Error searching Android software for '%s': %s", query, e)
            return []

    @classmethod
    async def _get_remote_file_size_mb(cls, url: str) -> float:
        """Quickly check Content-Length of a remote URL using HEAD request."""
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.head(url)
                if resp.status_code == 200:
                    cl = resp.headers.get("content-length")
                    if cl and cl.isdigit():
                        return round(int(cl) / (1024 * 1024), 1)
        except Exception:
            pass
        return 0.0

    @classmethod
    async def _winget_show(cls, package_id: str) -> Optional[Dict[str, Any]]:
        """Run `winget show` for a specific package ID and extract metadata."""
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

            # Detect extension
            lower_url = installer_url.lower()
            if ".msi" in lower_url:
                ext = "msi"
            elif ".zip" in lower_url:
                ext = "zip"
            else:
                ext = "exe"

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
    async def search_windows(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search Windows software using `winget search --source winget` and `winget show`.
        Returns a list of dicts with keys:
          name, package, version, size_mb, download_url, updated, platform
        """
        norm_query = cls._normalize_query(query)

        def _run_search():
            import subprocess
            return subprocess.run(
                ["winget", "search", "--source", "winget", norm_query],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=15,
            )

        try:
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
                if len(candidates) >= limit * 2:
                    break

            # Fetch details in parallel for candidates
            tasks = [cls._winget_show(c["id"]) for c in candidates]
            show_results = await asyncio.gather(*tasks, return_exceptions=True)

            results: List[Dict[str, Any]] = []
            for cand, show_res in zip(candidates, show_results):
                if not isinstance(show_res, dict) or not show_res.get("download_url"):
                    continue

                installer_url = show_res["download_url"]
                version = show_res.get("version") or cand["version"] or "نامشخص"
                ext = show_res.get("extension", "exe")
                updated = show_res.get("updated", "نامشخص")

                # Try getting remote size
                size_mb = await cls._get_remote_file_size_mb(installer_url)

                results.append(
                    {
                        "name": cand["name"],
                        "package": cand["id"],
                        "version": version,
                        "size_mb": size_mb,
                        "download_url": installer_url,
                        "updated": updated,
                        "platform": "windows",
                        "extension": ext,
                    }
                )

                if len(results) >= limit:
                    break

            return results
        except Exception as e:
            logger.exception("Error searching Windows software for '%s': %s", query, e)
            return []

    @classmethod
    async def download_file(
        cls,
        url: str,
        dest_dir: str = "downloads/software",
        filename: Optional[str] = None,
    ) -> str:
        """
        Download a file asynchronously and save to dest_dir.
        Returns the absolute path to the downloaded file.
        """
        Path(dest_dir).mkdir(parents=True, exist_ok=True)

        if not filename:
            # Infer filename from url
            clean_url = url.split("?")[0].split("#")[0]
            inferred = os.path.basename(clean_url)
            filename = sanitize_filename(inferred) or "software_file.bin"
        else:
            filename = sanitize_filename(filename)

        dest_path = os.path.join(dest_dir, filename)

        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(headers=headers, timeout=180.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=128 * 1024):
                        f.write(chunk)

        return os.path.abspath(dest_path)
