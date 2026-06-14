from __future__ import annotations

import re

from app.models import MediaEntry

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_EPISODE_RE = re.compile(r"(?P<series>.+?)[ ._\-]+S(?P<season>\d{1,2})E(?P<episode>\d{1,3})\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\((19|20)\d{2}\)")


def looks_like_m3u(text: str) -> bool:
    """Cheap sanity check that a response body is a playlist and not, e.g., an
    HTML error page returned by a provider that rejected the request."""
    head = text.lstrip()[:1000].upper()
    return head.startswith("#EXTM3U") or "#EXTINF" in head


def parse_m3u(text: str) -> list[MediaEntry]:
    """Parse a simple extended M3U playlist into media entries."""
    entries: list[MediaEntry] = []
    pending_meta: tuple[dict[str, str], str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == "#EXTM3U":
            continue
        if line.startswith("#EXTINF"):
            pending_meta = _parse_extinf(line)
            continue
        if line.startswith("#"):
            continue
        if pending_meta is None:
            entries.append(classify_entry({}, line.rsplit("/", 1)[-1] or line, line))
            continue
        attrs, display_name = pending_meta
        entries.append(classify_entry(attrs, display_name, line))
        pending_meta = None

    return entries


def _parse_extinf(line: str) -> tuple[dict[str, str], str]:
    attrs = {key: value for key, value in _ATTR_RE.findall(line)}
    display_name = line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "")
    return attrs, display_name


def _extract_year(value: str) -> int | None:
    match = _YEAR_RE.search(value)
    return int(match.group(0)[1:-1]) if match else None


def classify_entry(attrs: dict[str, str], display_name: str, url: str) -> MediaEntry:
    tvg_name = attrs.get("tvg-name") or None
    group_title = attrs.get("group-title") or None
    logo = attrs.get("tvg-logo") or None
    tvg_id = attrs.get("tvg-id") or None
    title = (tvg_name or display_name or url.rsplit("/", 1)[-1]).strip()

    episode_match = _EPISODE_RE.search(title)
    if episode_match:
        # Series episode: the SxxEyy pattern is the most reliable signal.
        return MediaEntry(
            title=title,
            url=url,
            kind="series",
            group_title=group_title,
            tvg_name=tvg_name,
            series_title=_clean_series_title(episode_match.group("series")),
            season=int(episode_match.group("season")),
            episode=int(episode_match.group("episode")),
            logo=logo,
            year=_extract_year(title),
        )

    # No episode pattern. On VOD-heavy XUI playlists, live channels carry an EPG
    # id (tvg-id) while on-demand movies do not, so that's the main signal; a
    # handful of group names also mark live TV explicitly.
    group_l = (group_title or "").lower()
    if tvg_id or any(word in group_l for word in ("live", "canais", "channels")):
        kind = "channel"
    else:
        kind = "movie"

    return MediaEntry(
        title=title,
        url=url,
        kind=kind,
        group_title=group_title,
        tvg_name=tvg_name,
        logo=logo,
        year=_extract_year(title),
    )


def _clean_series_title(value: str) -> str:
    cleaned = re.sub(r"[ ._\-]+$", "", value).replace(".", " ").replace("_", " ").strip()
    return _YEAR_RE.sub("", cleaned).strip()
