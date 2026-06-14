from app.catalog import Catalog
from app.main import _refresh_tmdb_aliases
from app.models import MediaEntry
from app.tmdb import Review


class FakeTmdb:
    def __init__(self):
        self.calls = []

    def lookup(self, title, year, kind):
        self.calls.append((title, year, kind))
        if title == "Nos Meandros da Lei":
            return Review(
                title="Nos Meandros da Lei",
                original_title="The Lincoln Lawyer",
                overview="",
                rating=None,
                votes=None,
                year=2022,
                poster=None,
                series_id=123,
            )
        return None


def test_catalog_lists_distinct_tmdb_alias_targets(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(title="Movie A", url="m1", kind="movie", year=2020),
        MediaEntry(title="Nos Meandros da Lei S01E01", url="s1", kind="series", series_title="Nos Meandros da Lei", season=1, episode=1, year=2022),
        MediaEntry(title="Nos Meandros da Lei S01E02", url="s2", kind="series", series_title="Nos Meandros da Lei", season=1, episode=2, year=2022),
    ])

    targets = catalog.tmdb_alias_targets()

    assert targets == [
        {"kind": "movie", "title": "Movie A", "year": 2020},
        {"kind": "series", "title": "Nos Meandros da Lei", "year": 2022},
    ]


def test_refresh_tmdb_aliases_updates_catalog_search_aliases(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(title="Nos Meandros da Lei S01E01", url="s1", kind="series", series_title="Nos Meandros da Lei", season=1, episode=1, year=2022),
        MediaEntry(title="Nos Meandros da Lei S01E02", url="s2", kind="series", series_title="Nos Meandros da Lei", season=1, episode=2, year=2022),
    ])

    stats = _refresh_tmdb_aliases(catalog, FakeTmdb())

    assert stats == {"checked": 1, "updated": 1, "misses": 0}
    assert [s.series_title for s in catalog.list_series(query="lincoln")] == ["Nos Meandros da Lei"]
