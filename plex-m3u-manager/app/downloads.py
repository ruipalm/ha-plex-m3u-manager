from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from app.models import MediaEntry

_BAD_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]+")
_SPACE_RUN = re.compile(r"\s+")


def sanitize_filename(value: str) -> str:
    cleaned = _BAD_FILENAME_CHARS.sub(" ", value).strip()
    cleaned = _SPACE_RUN.sub(" ", cleaned)
    return cleaned or "untitled"


def extension_from_url(url: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in {".ts", ".mp4", ".mkv", ".m4v", ".avi"}:
        return suffix
    return ".ts"


def destination_for_entry(entry: MediaEntry, movies_root: str | Path, series_root: str | Path) -> Path:
    extension = extension_from_url(entry.url)
    filename = sanitize_filename(entry.title) + extension
    if entry.kind == "series":
        series_title = sanitize_filename(entry.series_title or entry.title)
        season = entry.season or 1
        return Path(series_root) / series_title / f"Season {season:02d}" / filename
    return Path(movies_root) / filename
