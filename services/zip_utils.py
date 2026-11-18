import logging
import os
import shutil
import subprocess
import zipfile
from typing import List, Tuple

logger = logging.getLogger(__name__)


# split_method: "single" | "spanned" (zip -s, WinRAR/7-Zip) | "concat" (merge .zip.001+...)
ZipSplitResult = Tuple[List[str], str, str]

_INCOMPRESSIBLE_EXTS = frozenset(
    {
        ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv",
        ".mp3", ".m4a", ".ogg", ".aac", ".flac", ".opus",
        ".jpg", ".jpeg", ".png", ".webp", ".gif",
        ".apk", ".7z", ".rar", ".gz", ".xz", ".bz2", ".zip", ".zst",
    }
)


def _is_incompressible(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in _INCOMPRESSIBLE_EXTS


def make_zip_single(
    input_path: str,
    zip_path: str,
    arcname: str | None = None,
    compression_level: int = 6,
) -> str:
    if not arcname:
        arcname = os.path.basename(input_path)

    os.makedirs(os.path.dirname(zip_path) or ".", exist_ok=True)
    incompressible = _is_incompressible(input_path)
    compression = zipfile.ZIP_STORED if incompressible else zipfile.ZIP_DEFLATED
    zf_kwargs = {"mode": "w", "compression": compression}
    if not incompressible:
        zf_kwargs["compresslevel"] = compression_level

    with zipfile.ZipFile(zip_path, **zf_kwargs) as zf:
        zf.write(input_path, arcname=arcname)

    return zip_path


def _collect_spanned_parts(out_dir: str, basename: str) -> List[str]:
    """ترتیب صحیح: name.zip سپس name.z01, name.z02, ..."""
    ordered: List[str] = []
    main = os.path.join(out_dir, f"{basename}.zip")
    if os.path.isfile(main):
        ordered.append(main)
    for i in range(1, 999):
        seg = os.path.join(out_dir, f"{basename}.z{i:02d}")
        if os.path.isfile(seg):
            ordered.append(seg)
        else:
            break
    return ordered


def _try_spanned_zip(
    input_path: str,
    out_dir: str,
    zip_basename: str,
    max_part_bytes: int,
) -> List[str] | None:
    """
    ساخت ZIP تقسیم‌شده استاندارد با zip -s (قابل باز شدن در 7-Zip / WinRAR).
    """
    zip_cmd = shutil.which("zip")
    if not zip_cmd:
        return None

    mb = max(1, max_part_bytes // (1024 * 1024))
    archive_zip = os.path.join(out_dir, f"{zip_basename}.zip")

    # حذف باقی‌ماندهٔ قبلی
    for old in _collect_spanned_parts(out_dir, zip_basename):
        try:
            os.remove(old)
        except OSError:
            pass

    try:
        cmd = [zip_cmd, "-j"]
        if _is_incompressible(input_path):
            cmd.append("-0")
        cmd.extend([f"-s{mb}m", archive_zip, input_path])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            logger.warning("zip -s failed: %s", proc.stderr or proc.stdout)
            return None
        parts = _collect_spanned_parts(out_dir, zip_basename)
        return parts if parts else None
    except Exception as e:
        logger.warning("zip -s error: %s", e)
        return None


_STREAM_CHUNK_BYTES = 4 * 1024 * 1024  # 4 MB streaming buffer


def split_file_concat_parts(
    input_path: str,
    max_part_bytes: int,
    archive_basename: str,
) -> List[str]:
    """
    تقسیم باینری؛ هر پارت به تنهایی ZIP نیست.
    نام: archive.zip.001, archive.zip.002 — پس از ادغام با copy/cat فایل .zip ساخته می‌شود.
    """
    if max_part_bytes <= 0:
        raise ValueError("max_part_bytes must be > 0")

    file_size = os.path.getsize(input_path)
    if file_size <= max_part_bytes:
        return [input_path]

    base_dir = os.path.dirname(input_path) or "."
    part_paths: List[str] = []
    part_index = 1

    with open(input_path, "rb") as src:
        while True:
            part_path = os.path.join(
                base_dir, f"{archive_basename}.zip.{part_index:03d}"
            )
            written = 0
            with open(part_path, "wb") as dst:
                while written < max_part_bytes:
                    to_read = min(_STREAM_CHUNK_BYTES, max_part_bytes - written)
                    chunk = src.read(to_read)
                    if not chunk:
                        break
                    dst.write(chunk)
                    written += len(chunk)

            if written == 0:
                try:
                    os.remove(part_path)
                except OSError:
                    pass
                break

            part_paths.append(part_path)
            part_index += 1

    return part_paths


def part_display_filename(
    file_path: str,
    archive_basename: str,
    part_index: int,
    total_parts: int,
    split_method: str,
) -> str:
    """نام فایلی که کاربر هنگام دانلود می‌بیند."""
    if total_parts == 1:
        return f"{archive_basename}.zip"
    if split_method == "spanned":
        if part_index == 1:
            return f"{archive_basename}.zip"
        return f"{archive_basename}.z{part_index - 1:02d}"
    return f"{archive_basename}.zip.{part_index:03d}"


def format_merge_instructions(
    archive_basename: str,
    total_parts: int,
    split_method: str,
) -> str:
    if total_parts <= 1:
        return ""

    if split_method == "spanned":
        return (
            f"📦 فایل در {total_parts} پارت ارسال شد ({archive_basename}.zip و .z01 …)\n\n"
            "✅ روش باز کردن:\n"
            "۱) همه پارت‌ها را در یک پوشه (Folder) مشترک دانلود و ذخیره کنید.\n"
            "۲) فقط روی فایل "
            f"`{archive_basename}.zip`"
            " کلیک کرده و با برنامه‌های WinRAR، 7-Zip یا ZArchiver آن را Extract (استخراج) کنید.\n\n"
            "⚠️ توجه: پارت‌ها به تنهایی باز نمی‌شوند و باید همه در کنار هم باشند."
        )

    # concat (راهنمای جامع و کاربرپسند)
    return (
        f"📥 **راهنمای باز کردن فایل در {total_parts} پارت**\n\n"
        "⚠️ **توجه مهم:** این پارت‌ها تکی کار نمی‌کنند! حتماً همه پارت‌ها را در **یک پوشه مشترک** دانلود کنید.\n\n"
        "📱 **اندروید (Android):**\n"
        "برنامه **ZArchiver** یا RAR را نصب کنید. فقط روی پارت اول "
        f"(`{archive_basename}.zip.001`)"
        " ضربه بزنید و گزینه Extract here (استخراج در اینجا) را انتخاب کنید.\n\n"
        "💻 **ویندوز (PC):**\n"
        "برنامه WinRAR یا 7-Zip را نصب کنید. روی پارت اول "
        f"(`{archive_basename}.zip.001`)"
        " کلیک راست کرده و **Extract Here** را بزنید.\n\n"
        "🍏 **آیفون و آیپد (iOS):**\n"
        "برنامه iZip یا Unzip را نصب کرده و پارت اول را با آن باز کنید تا خودکار استخراج شود.\n\n"
        "🐧 **مک و لینوکس:**\n"
        "در ترمینال به پوشه فایل‌ها بروید و این دستور را اجرا کنید:\n"
        f"`cat {archive_basename}.zip.* > {archive_basename}.zip`\n"
        "سپس فایل جدید را استخراج کنید."
    )

def build_zip_and_split(
    input_path: str,
    out_dir: str,
    zip_basename: str,
    max_part_bytes: int,
) -> ZipSplitResult:
    """
    Returns (part_paths_ordered, archive_basename, split_method).
    part_paths: مسیر فایل‌هایی که باید ارسال شوند (به ترتیب).
    """
    os.makedirs(out_dir, exist_ok=True)
    archive_basename = zip_basename

    # 1. If input is already a zip file, avoid double-zipping
    if input_path.lower().endswith(".zip"):
        file_size = os.path.getsize(input_path)
        if file_size <= max_part_bytes:
            return [input_path], archive_basename, "single"
        parts = split_file_concat_parts(input_path, max_part_bytes, archive_basename)
        return parts, archive_basename, "concat"

    # 2. For clearly multi-part files (already compressed or >> max_part_bytes),
    # try spanned zip directly first; if unavailable or failed, fall back straight to
    # single ZIP + concat split without retrying spanned zip a second time or leaving
    # an extra full-size .zip copy on disk.
    input_size = os.path.getsize(input_path)
    spanned_already_tried = False
    if input_size > max_part_bytes and (_is_incompressible(input_path) or input_size > max_part_bytes * 2):
        spanned_already_tried = True
        spanned = _try_spanned_zip(input_path, out_dir, archive_basename, max_part_bytes)
        if spanned:
            method = "single" if len(spanned) == 1 else "spanned"
            return spanned, archive_basename, method

    # 3. Build a standard, valid single ZIP
    zip_path = os.path.join(out_dir, f"{archive_basename}.zip")
    make_zip_single(input_path=input_path, zip_path=zip_path)

    # If the clean ZIP fits in a single part, return it directly!
    if os.path.getsize(zip_path) <= max_part_bytes:
        return [zip_path], archive_basename, "single"

    # 4. If file exceeds max_part_bytes and spanned zip hasn't been attempted yet, try it once
    if not spanned_already_tried:
        backup_zip = f"{zip_path}.single_tmp"
        try:
            if os.path.isfile(backup_zip):
                os.remove(backup_zip)
            os.replace(zip_path, backup_zip)
        except OSError:
            backup_zip = None

        spanned = _try_spanned_zip(input_path, out_dir, archive_basename, max_part_bytes)
        if spanned and len(spanned) > 1:
            if backup_zip and os.path.isfile(backup_zip):
                try:
                    os.remove(backup_zip)
                except OSError:
                    pass
            return spanned, archive_basename, "spanned"

        for leftover in _collect_spanned_parts(out_dir, archive_basename):
            try:
                os.remove(leftover)
            except OSError:
                pass
        if backup_zip and os.path.isfile(backup_zip):
            os.replace(backup_zip, zip_path)

    parts = split_file_concat_parts(zip_path, max_part_bytes, archive_basename)
    # Remove the intermediate monolithic .zip once concat parts are written
    if len(parts) > 1 and zip_path not in parts and os.path.isfile(zip_path):
        try:
            os.remove(zip_path)
        except OSError:
            pass
    return parts, archive_basename, "concat"
