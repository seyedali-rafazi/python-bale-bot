import os
import zipfile
from typing import List, Tuple


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


def split_file_by_size(input_path: str, max_part_bytes: int) -> List[str]:
    """
    Splits a file into sequential parts, each <= max_part_bytes.
    Returns list of part paths in order.
    """
    if max_part_bytes <= 0:
        raise ValueError("max_part_bytes must be > 0")

    file_size = os.path.getsize(input_path)
    if file_size <= max_part_bytes:
        return [input_path]

    base_dir = os.path.dirname(input_path) or "."
    base_name = os.path.basename(input_path)
    name_root = base_name

    part_paths: List[str] = []
    part_index = 1

    with open(input_path, "rb") as src:
        while True:
            chunk = src.read(max_part_bytes)
            if not chunk:
                break
            part_path = os.path.join(base_dir, f"{name_root}.part{part_index:03d}")
            with open(part_path, "wb") as dst:
                dst.write(chunk)
            part_paths.append(part_path)
            part_index += 1

    return part_paths


def build_zip_and_split(
    input_path: str,
    out_dir: str,
    zip_basename: str,
    max_part_bytes: int,
) -> Tuple[str, List[str]]:
    """
    Creates zip file and splits it if needed. Returns (zip_path, part_paths).
    If no split needed, part_paths will contain only zip_path.
    """
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"{zip_basename}.zip")
    make_zip_single(input_path=input_path, zip_path=zip_path)
    parts = split_file_by_size(zip_path, max_part_bytes=max_part_bytes)
    return zip_path, parts

