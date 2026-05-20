import os
import shutil
import subprocess
import zipfile
from typing import List, Tuple


# split_method: "single" | "spanned" (zip -s, WinRAR/7-Zip) | "concat" (merge .zip.001+...)
ZipSplitResult = Tuple[List[str], str, str]


def make_zip_single(
    input_path: str,
    zip_path: str,
    arcname: str | None = None,
    compression_level: int = 6,
) -> str:
    if not arcname:
        arcname = os.path.basename(input_path)

    os.makedirs(os.path.dirname(zip_path) or ".", exist_ok=True)

    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=compression_level,
    ) as zf:
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
        proc = subprocess.run(
            [zip_cmd, "-j", f"-s{mb}m", archive_zip, input_path],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            print(f"zip -s failed: {proc.stderr or proc.stdout}")
            return None
        parts = _collect_spanned_parts(out_dir, zip_basename)
        return parts if parts else None
    except Exception as e:
        print(f"zip -s error: {e}")
        return None


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
            chunk = src.read(max_part_bytes)
            if not chunk:
                break
            part_path = os.path.join(
                base_dir, f"{archive_basename}.zip.{part_index:03d}"
            )
            with open(part_path, "wb") as dst:
                dst.write(chunk)
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
            "۱) همه پارت‌ها را در یک پوشه ذخیره کنید.\n"
            "۲) فقط فایل "
            f"`{archive_basename}.zip`"
            " را با WinRAR، 7-Zip یا ZArchiver باز کنید.\n"
            "(نیازی به ادغام دستی نیست — این فرمت split zip استاندارد است.)\n\n"
            "⚠️ هر پارت جدا قابل استخراج نیست."
        )

    # concat
    parts_expr = "+".join(
        f"{archive_basename}.zip.{i:03d}" for i in range(1, total_parts + 1)
    )
    return (
        f"📦 فایل در {total_parts} پارت ارسال شد.\n\n"
        "⚠️ هر پارت به تنهایی ZIP معتبر نیست — اول ادغام کنید، بعد Extract.\n\n"
        "✅ ویندوز (CMD در پوشه دانلود):\n"
        f"`copy /b {parts_expr} {archive_basename}.zip`\n\n"
        "✅ لینوکس / مک:\n"
        f"`cat {archive_basename}.zip.* > {archive_basename}.zip`\n\n"
        "✅ اندروید: ZArchiver → ادغام پارت‌ها (Merge) → سپس باز کردن "
        f"{archive_basename}.zip"
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

    spanned = _try_spanned_zip(input_path, out_dir, archive_basename, max_part_bytes)
    if spanned:
        method = "single" if len(spanned) == 1 else "spanned"
        main_zip = os.path.join(out_dir, f"{archive_basename}.zip")
        return spanned, archive_basename, method

    zip_path = os.path.join(out_dir, f"{archive_basename}.zip")
    make_zip_single(input_path=input_path, zip_path=zip_path)

    if os.path.getsize(zip_path) <= max_part_bytes:
        return [zip_path], archive_basename, "single"

    parts = split_file_concat_parts(zip_path, max_part_bytes, archive_basename)
    return parts, archive_basename, "concat"
