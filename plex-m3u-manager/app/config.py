from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class AppConfig:
    m3u_url: str = ""
    movies_path: str = "/share/plex_movies"
    series_path: str = "/share/plex_series"
    database_path: str = "/data/catalog.sqlite"

    def masked_m3u_url(self) -> str:
        if not self.m3u_url:
            return ""
        parts = urlsplit(self.m3u_url)
        query = urlencode(
            [(key, "MASKED" if key.lower() in {"username", "password", "token"} else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
        )
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def load_config(options_path: str | Path = "/data/options.json") -> AppConfig:
    options = {}
    path = Path(options_path)
    if path.exists():
        options = json.loads(path.read_text())

    default_db = "/data/catalog.sqlite" if path.exists() else "runtime/catalog.sqlite"

    return AppConfig(
        m3u_url=os.getenv("M3U_URL", options.get("m3u_url", "")),
        movies_path=os.getenv("MOVIES_PATH", options.get("movies_path", "/share/plex_movies")),
        series_path=os.getenv("SERIES_PATH", options.get("series_path", "/share/plex_series")),
        database_path=os.getenv("DATABASE_PATH", options.get("database_path", default_db)),
    )
