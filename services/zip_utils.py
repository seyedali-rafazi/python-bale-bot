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
