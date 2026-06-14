from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from app.models import Category, MediaEntry, SeriesSummary

_COLUMNS = ("title", "url", "kind", "group_title", "tvg_name", "series_title", "season", "episode", "logo", "year")


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
                    episode INTEGER,
                    logo TEXT,
                    year INTEGER
                )
                """
            )
            # Migrate older databases that predate the logo/year columns.
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(entries)")}
            for column, ddl in (("logo", "logo TEXT"), ("year", "year INTEGER")):
                if column not in existing:
                    conn.execute(f"ALTER TABLE entries ADD COLUMN {ddl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_group ON entries(group_title)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_series ON entries(series_title)")

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
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        with self._connect() as conn:
            conn.execute("DELETE FROM entries")
            conn.executemany(
                f"INSERT OR IGNORE INTO entries ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [
                    (entry.title, entry.url, entry.kind, entry.group_title, entry.tvg_name,
                     entry.series_title, entry.season, entry.episode, entry.logo, entry.year)
                    for entry in unique_entries
                ],
            )

    # -- counts -------------------------------------------------------------

    def kind_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT kind, COUNT(*) AS n FROM entries GROUP BY kind").fetchall()
        return {row["kind"]: row["n"] for row in rows}

    def categories(self, kind: str | None = None) -> list[Category]:
        clause, params = ("WHERE kind = ?", [kind]) if kind else ("", [])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT group_title AS name, COUNT(*) AS n FROM entries
                {clause}
                {'AND' if clause else 'WHERE'} group_title IS NOT NULL AND group_title <> ''
                GROUP BY group_title ORDER BY n DESC
                """,
                params,
            ).fetchall()
        return [Category(name=row["name"], count=row["n"]) for row in rows]

    # -- movies -------------------------------------------------------------

    def list_movies(self, query: str = "", group: str | None = None, sort: str = "title",
                    limit: int = 60, offset: int = 0) -> list[MediaEntry]:
        where, params = self._filter("movie", query, group)
        order = {"title": "title COLLATE NOCASE", "year": "year DESC, title COLLATE NOCASE"}.get(sort, "title COLLATE NOCASE")
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM entries {where} ORDER BY {order} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def count_movies(self, query: str = "", group: str | None = None) -> int:
        where, params = self._filter("movie", query, group)
        with self._connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM entries {where}", params).fetchone()[0]

    # -- series -------------------------------------------------------------

    def list_series(self, query: str = "", group: str | None = None, sort: str = "title",
                    limit: int = 60, offset: int = 0) -> list[SeriesSummary]:
        where, params = self._filter("series", query, group, title_column="series_title")
        order = {"title": "name COLLATE NOCASE", "year": "year DESC, name COLLATE NOCASE"}.get(sort, "name COLLATE NOCASE")
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT COALESCE(series_title, title) AS name,
                       MAX(group_title) AS group_title,
                       MAX(logo) AS logo,
                       MAX(year) AS year,
                       COUNT(DISTINCT season) AS seasons,
                       COUNT(*) AS episodes
                FROM entries {where}
                GROUP BY name
                ORDER BY {order}
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return [
            SeriesSummary(series_title=row["name"], group_title=row["group_title"], logo=row["logo"],
                          seasons=row["seasons"], episodes=row["episodes"], year=row["year"])
            for row in rows
        ]

    def count_series(self, query: str = "", group: str | None = None) -> int:
        where, params = self._filter("series", query, group, title_column="series_title")
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 FROM entries {where} GROUP BY COALESCE(series_title, title))",
                params,
            ).fetchone()[0]

    def series_detail(self, series_title: str) -> dict[int, list[MediaEntry]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM entries
                WHERE kind = 'series' AND COALESCE(series_title, title) = ?
                ORDER BY COALESCE(season, 1), COALESCE(episode, 0), title
                """,
                (series_title,),
            ).fetchall()
        seasons: dict[int, list[MediaEntry]] = defaultdict(list)
        for row in rows:
            entry = _entry_from_row(row)
            seasons[entry.season or 1].append(entry)
        return dict(seasons)

    # -- single / season helpers -------------------------------------------

    def get(self, entry_id: int) -> MediaEntry:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return _entry_from_row(row)

    def search(self, query: str = "", kind: str | None = None, limit: int = 200) -> list[MediaEntry]:
        where, params = self._filter(kind, query, None)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM entries {where} ORDER BY kind, COALESCE(series_title, title), season, episode, title LIMIT ?",
                [*params, limit],
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def season_entries(self, series_title: str, season: int) -> list[MediaEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM entries
                WHERE kind = 'series' AND COALESCE(series_title, title) = ? AND COALESCE(season, 1) = ?
                ORDER BY episode, title
                """,
                (series_title, season),
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def series_tree(self) -> dict[str, dict[int, list[MediaEntry]]]:
        tree: dict[str, dict[int, list[MediaEntry]]] = defaultdict(lambda: defaultdict(list))
        for entry in self.search(kind="series", limit=100000):
            tree[entry.series_title or entry.title][entry.season or 1].append(entry)
        return {series: dict(seasons) for series, seasons in tree.items()}

    # -- internals ----------------------------------------------------------

    def _filter(self, kind: str | None, query: str, group: str | None,
                title_column: str = "title") -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if group:
            clauses.append("group_title = ?")
            params.append(group)
        if query:
            clauses.append(f"LOWER(COALESCE({title_column}, title)) LIKE ?")
            params.append(f"%{query.lower()}%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return where, params


def _entry_from_row(row: sqlite3.Row) -> MediaEntry:
    keys = row.keys()
    return MediaEntry(
        title=row["title"],
        url=row["url"],
        kind=row["kind"],
        group_title=row["group_title"],
        tvg_name=row["tvg_name"],
        series_title=row["series_title"],
        season=row["season"],
        episode=row["episode"],
        logo=row["logo"] if "logo" in keys else None,
        year=row["year"] if "year" in keys else None,
        id=row["id"],
    )
