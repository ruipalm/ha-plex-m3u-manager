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
    logo: str | None = None
    year: int | None = None
    id: int | None = None


@dataclass(frozen=True)
class SeriesSummary:
    """One row per distinct series, for the browse grid."""
    series_title: str
    group_title: str | None
    logo: str | None
    seasons: int
    episodes: int
    year: int | None = None


@dataclass(frozen=True)
class Category:
    name: str
    count: int


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
