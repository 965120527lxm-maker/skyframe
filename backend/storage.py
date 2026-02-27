"""
Storage abstraction.
Current: local disk.  Future: swap to S3 presigned URLs.
"""

from pathlib import Path
from datetime import datetime
from config import STORAGE_DIR


def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def generate_storage_key(upload_id: str, filename: str) -> str:
    now = datetime.utcnow()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return f"uploads/{now.year}/{now.month:02d}/{now.day:02d}/{upload_id}_{safe}"


def generate_output_key(job_id: str, filename: str) -> str:
    now = datetime.utcnow()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return f"outputs/{now.year}/{now.month:02d}/{now.day:02d}/{job_id}_{safe}"


def get_file_path(storage_key: str) -> Path:
    return STORAGE_DIR / storage_key


async def save_file(storage_key: str, file_obj) -> int:
    dest = get_file_path(storage_key)
    _ensure_dir(dest)
    total = 0
    with open(dest, "wb") as f:
        while chunk := await file_obj.read(1024 * 1024):
            f.write(chunk)
            total += len(chunk)
    return total


def save_bytes(storage_key: str, data: bytes) -> int:
    dest = get_file_path(storage_key)
    _ensure_dir(dest)
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def file_exists(storage_key: str) -> bool:
    return get_file_path(storage_key).exists()


def delete_file(storage_key: str):
    path = get_file_path(storage_key)
    if path.exists():
        path.unlink()
