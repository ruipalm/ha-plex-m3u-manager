from __future__ import annotations

import os
from pathlib import Path

from app.models import MediaFile, SpaceInfo

_MEDIA_EXTENSIONS = {".ts", ".mp4", ".mkv", ".avi", ".mov", ".m4v"}


def human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} B"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def get_space_info(path: str | Path) -> SpaceInfo:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    usage = os.statvfs(root)
    total = usage.f_frsize * usage.f_blocks
    free = usage.f_frsize * usage.f_bavail
    used = total - free
    return SpaceInfo(path=str(root), total_bytes=total, used_bytes=used, free_bytes=free)


def list_media_files(root: str | Path) -> list[MediaFile]:
    root_path = Path(root)
    if not root_path.exists():
        return []
    files: list[MediaFile] = []
    for path in root_path.rglob("*"):
        if path.is_file() and path.suffix.lower() in _MEDIA_EXTENSIONS:
            stat = path.stat()
            files.append(MediaFile(str(path.relative_to(root_path)), stat.st_size, stat.st_mtime))
    return sorted(files, key=lambda item: item.relative_path.lower())


def delete_within_root(root: str | Path, relative_path: str) -> None:
    root_path = Path(root).resolve()
    target = (root_path / relative_path).resolve()
    if root_path != target and root_path not in target.parents:
        raise ValueError("Refusing to delete outside configured media root")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(relative_path)
    target.unlink()
