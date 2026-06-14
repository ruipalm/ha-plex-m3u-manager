from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx

# Optional enrichment. The playlist gives us titles and (usually) poster art,
# but no synopsis or rating. When the user configures a free TMDB API key we
# look the title up and show review-style information on the detail pages.
# Without a key the app works exactly the same, minus the review block.

_BASE = "https://api.themoviedb.org/3"
_IMG = "https://image.tmdb.org/t/p/w342"


@dataclass(frozen=True)
class Review:
    title: str
    overview: str
    rating: float | None
    votes: int | None
    year: int | None
    poster: str | None
    series_id: int | None = None


@dataclass(frozen=True)
class EpisodeInfo:
    name: str
    overview: str
    air_date: str | None
    still: str | None


class Tmdb:
    def __init__(self, api_key: str, cache_dir: str | Path, language: str = "pt-PT"):
        self.api_key = api_key
        self.language = language
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    def lookup(self, title: str, year: int | None, kind: str) -> Review | None:
        if not self.api_key or not title:
            return None
        cache_key = f"{kind}|{title}|{year}|{self.language}"
        cached = self._cache_path(cache_key)
        if cached.exists():
            data = json.loads(cached.read_text())
            if data is None:
                return None
            review = Review(**data)
            # Invalidate stale cache entries that pre-date series_id storage.
            if kind == "series" and review.series_id is None:
                cached.unlink()
            else:
                return review

        search = "tv" if kind == "series" else "movie"
        params = {"api_key": self.api_key, "language": self.language, "query": title}
        if year and search == "movie":
            params["year"] = year
        elif year:
            params["first_air_date_year"] = year
        try:
            response = httpx.get(f"{_BASE}/search/{search}", params=params, timeout=15)
            response.raise_for_status()
            results = response.json().get("results") or []
        except Exception:
            return None

        if not results:
            cached.write_text(json.dumps(None))
            return None
        top = results[0]
        date = top.get("release_date") or top.get("first_air_date") or ""
        review = Review(
            title=top.get("title") or top.get("name") or title,
            overview=top.get("overview") or "",
            rating=round(top["vote_average"], 1) if top.get("vote_average") else None,
            votes=top.get("vote_count"),
            year=int(date[:4]) if date[:4].isdigit() else year,
            poster=(_IMG + top["poster_path"]) if top.get("poster_path") else None,
            series_id=top.get("id") if kind == "series" else None,
        )
        cached.write_text(json.dumps(review.__dict__))
        return review

    def season_episodes(self, series_id: int, season: int) -> dict[int, EpisodeInfo]:
        cache_key = f"season|{series_id}|{season}|{self.language}"
        cached = self._cache_path(cache_key)
        if cached.exists():
            data = json.loads(cached.read_text())
            return {int(k): EpisodeInfo(**v) for k, v in data.items()} if data else {}
        try:
            response = httpx.get(
                f"{_BASE}/tv/{series_id}/season/{season}",
                params={"api_key": self.api_key, "language": self.language},
                timeout=15,
            )
            response.raise_for_status()
            episodes = response.json().get("episodes") or []
        except Exception:
            cached.write_text(json.dumps({}))
            return {}
        result: dict[int, EpisodeInfo] = {}
        for ep in episodes:
            ep_num = ep.get("episode_number")
            if ep_num is not None:
                result[ep_num] = EpisodeInfo(
                    name=ep.get("name") or "",
                    overview=ep.get("overview") or "",
                    air_date=ep.get("air_date") or None,
                    still=(_IMG + ep["still_path"]) if ep.get("still_path") else None,
                )
        cached.write_text(json.dumps({str(k): v.__dict__ for k, v in result.items()}))
        return result
