from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MediaEntry:
    title: str
    url: str
    kind: str  # movie | series | channel | unknown
    group_title: str | None = None
    tvg_name: str | None = None
    series_title: str | None = None
    season: int | None = None
    episode: int | None = None
    id: int | None = None


@dataclass(frozen=True)
class SpaceInfo:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int


@dataclass(frozen=True)
class MediaFile:
    relative_path: str
    size_bytes: int
    modified_ts: float
