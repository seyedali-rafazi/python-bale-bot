# services/kaggle.py
"""
Kaggle API service.

Authentication: uses the KAGGLE_API_TOKEN environment variable (new token format).
All blocking Kaggle SDK calls are wrapped in asyncio.to_thread() to avoid
blocking the event loop.
"""

import asyncio
import os
import shutil
import threading
import zipfile
import uuid
import logging
from pathlib import Path
from typing import List, Tuple

from services.zip_utils import _is_incompressible

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
MAX_PART_BYTES = 49 * 1024 * 1024  # 49 MB per part (leave 1 MB margin for Bale)
KAGGLE_TEMP_BASE = "kaggle_temp"

_kaggle_api = None
_kaggle_token = None
_kaggle_api_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# Internal: build authenticated API object
# ──────────────────────────────────────────────────────────────────────────────
def _get_api():
    """Return a cached authenticated KaggleApiExtended instance."""
    global _kaggle_api, _kaggle_token
    token = os.getenv("KAGGLE_API_TOKEN", "")
    if not token:
        raise RuntimeError("KAGGLE_API_TOKEN is not set in the environment.")

    with _kaggle_api_lock:
        if _kaggle_api is not None and _kaggle_token == token:
            return _kaggle_api

        # The new token format (KGAT_…) is set via the env var directly.
        os.environ["KAGGLE_API_TOKEN"] = token

        try:
            # kaggle SDK < 1.7 used KaggleApiExtended
            from kaggle.api.kaggle_api_extended import KaggleApiExtended  # type: ignore
            api = KaggleApiExtended()
        except ImportError:
            # kaggle SDK >= 1.7 renamed the class to KaggleApi
            from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore
            api = KaggleApi()
        api.authenticate()
        _kaggle_api = api
        _kaggle_token = token
        return api


# ──────────────────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────────────────
def _search_datasets_sync(query: str, max_results: int = 8) -> list:
    api = _get_api()
    results = api.dataset_list(search=query)
    return list(results)[:max_results]


def _list_popular_datasets_sync(max_results: int = 8) -> list:
    api = _get_api()
    results = api.dataset_list(sort_by="votes")
    return list(results)[:max_results]


async def search_datasets(query: str, max_results: int = 8) -> list:
    """Async wrapper: search Kaggle datasets by keyword."""
    return await asyncio.to_thread(_search_datasets_sync, query, max_results)


async def list_popular_datasets(max_results: int = 8) -> list:
    """Async wrapper: list most-voted datasets."""
    return await asyncio.to_thread(_list_popular_datasets_sync, max_results)


# ──────────────────────────────────────────────────────────────────────────────
# Format helpers
# ──────────────────────────────────────────────────────────────────────────────
def format_dataset_size(dataset) -> str:
    """Return human-readable size string from dataset object."""
    try:
        size_bytes = dataset.totalBytes
        if size_bytes is None:
            return "نامشخص"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / 1024 ** 2:.1f} MB"
        else:
            return f"{size_bytes / 1024 ** 3:.1f} GB"
    except Exception:
        return "نامشخص"


def dataset_ref(dataset) -> str:
    """Return 'owner/name' reference string."""
    return f"{dataset.ref}"


# ──────────────────────────────────────────────────────────────────────────────
# Download
# ──────────────────────────────────────────────────────────────────────────────
def _download_dataset_sync(ref: str, dest_dir: str) -> str:
    """
    Downloads and unzips a Kaggle dataset to dest_dir.
    Returns the path of the directory containing the unzipped files.
    """
    api = _get_api()
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    # Download zip file then unzip
    api.dataset_download_files(ref, path=dest_dir, unzip=True, quiet=False)
    return dest_dir


async def download_dataset(ref: str, dest_dir: str) -> str:
    """Async wrapper: download and unzip a dataset."""
    return await asyncio.to_thread(_download_dataset_sync, ref, dest_dir)


# ──────────────────────────────────────────────────────────────────────────────
# ZIP splitter — splits a directory of files into ≤49 MB parts
# ──────────────────────────────────────────────────────────────────────────────
def split_into_20mb_zips(src_dir: str, out_dir: str, base_name: str) -> List[str]:
    """
    Walk src_dir, collect all files, and pack them into sequential ZIP
    parts each no larger than MAX_PART_BYTES (49 MB).

    Returns a list of absolute paths to the created ZIP files.
    If the dataset is empty, returns an empty list.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # Gather all files with relative paths
    all_files: List[Tuple[str, str]] = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            abs_path = os.path.join(root, f)
            rel_path = os.path.relpath(abs_path, src_dir)
            all_files.append((abs_path, rel_path))

    if not all_files:
        return []

    part_paths: List[str] = []
    part_num = 1
    current_zip_path = os.path.join(out_dir, f"{base_name}_part{part_num}.zip")
    current_zip = zipfile.ZipFile(current_zip_path, "w", zipfile.ZIP_DEFLATED)
    current_size = 0

    try:
        for abs_path, rel_path in all_files:
            file_size = os.path.getsize(abs_path)

            # If adding this file would exceed limit AND we already have something in the zip
            if current_size + file_size > MAX_PART_BYTES and current_size > 0:
                current_zip.close()
                part_paths.append(current_zip_path)
                part_num += 1
                current_zip_path = os.path.join(out_dir, f"{base_name}_part{part_num}.zip")
                current_zip = zipfile.ZipFile(current_zip_path, "w", zipfile.ZIP_DEFLATED)
                current_size = 0

            # Skip DEFLATE CPU burn on already-compressed media/archives
            compress_type = (
                zipfile.ZIP_STORED
                if _is_incompressible(abs_path) or abs_path.lower().endswith(".parquet")
                else zipfile.ZIP_DEFLATED
            )
            current_zip.write(abs_path, rel_path, compress_type=compress_type)
            current_size += file_size
    finally:
        try:
            current_zip.close()
        except Exception:
            pass

    if current_size > 0:
        part_paths.append(current_zip_path)

    return part_paths


async def split_into_20mb_zips_async(
    src_dir: str, out_dir: str, base_name: str
) -> List[str]:
    """Async wrapper for split_into_20mb_zips."""
    return await asyncio.to_thread(split_into_20mb_zips, src_dir, out_dir, base_name)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def make_temp_dirs() -> Tuple[str, str]:
    """Create and return (download_dir, zip_output_dir) inside kaggle_temp/."""
    uid = uuid.uuid4().hex
    dl_dir = os.path.join(KAGGLE_TEMP_BASE, uid, "dl")
    zip_dir = os.path.join(KAGGLE_TEMP_BASE, uid, "zips")
    Path(dl_dir).mkdir(parents=True, exist_ok=True)
    Path(zip_dir).mkdir(parents=True, exist_ok=True)
    return dl_dir, zip_dir


def cleanup_temp(path: str) -> None:
    """Remove a temp directory tree silently."""
    try:
        parent = str(Path(path).parent)
        shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        pass
