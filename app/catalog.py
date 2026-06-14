from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from app.models import MediaEntry


class Catalog:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    group_title TEXT,
                    tvg_name TEXT,
                    series_title TEXT,
                    season INTEGER,
                    episode INTEGER
                )
                """
            )

    def replace_entries(self, entries: list[MediaEntry]) -> None:
        # M3U playlists frequently repeat the same stream URL (e.g. an episode
        # listed in more than one group). The table enforces UNIQUE(url), so we
        # deduplicate by URL before inserting; without this a handful of repeats
        # would abort the whole import and leave the catalog empty.
        seen: set[str] = set()
        unique_entries: list[MediaEntry] = []
        for entry in entries:
            if entry.url in seen:
                continue
            seen.add(entry.url)
            unique_entries.append(entry)
        with self._connect() as conn:
            conn.execute("DELETE FROM entries")
            conn.executemany(
                """
                INSERT OR IGNORE INTO entries (title, url, kind, group_title, tvg_name, series_title, season, episode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (entry.title, entry.url, entry.kind, entry.group_title, entry.tvg_name, entry.series_title, entry.season, entry.episode)
                    for entry in unique_entries
                ],
            )

    def search(self, query: str = "", kind: str | None = None, limit: int = 200) -> list[MediaEntry]:
        clauses = []
        params: list[object] = []
        if query:
            clauses.append("LOWER(title) LIKE ?")
            params.append(f"%{query.lower()}%")
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM entries{where} ORDER BY kind, COALESCE(series_title, title), season, episode, title LIMIT ?",
                params,
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def get(self, entry_id: int) -> MediaEntry:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return _entry_from_row(row)

    def season_entries(self, series_title: str, season: int) -> list[MediaEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM entries
                WHERE kind = 'series' AND series_title = ? AND COALESCE(season, 1) = ?
                ORDER BY episode, title
                """,
                (series_title, season),
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def series_tree(self) -> dict[str, dict[int, list[MediaEntry]]]:
        tree: dict[str, dict[int, list[MediaEntry]]] = defaultdict(lambda: defaultdict(list))
        for entry in self.search(kind="series", limit=10000):
            tree[entry.series_title or entry.title][entry.season or 1].append(entry)
        return {series: dict(seasons) for series, seasons in tree.items()}


def _entry_from_row(row: sqlite3.Row) -> MediaEntry:
    return MediaEntry(
        title=row["title"],
        url=row["url"],
        kind=row["kind"],
        group_title=row["group_title"],
        tvg_name=row["tvg_name"],
        series_title=row["series_title"],
        season=row["season"],
        episode=row["episode"],
        id=row["id"],
    )
