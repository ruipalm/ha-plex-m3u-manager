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
            return Review(**data) if data else None

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
        )
        cached.write_text(json.dumps(review.__dict__))
        return review
