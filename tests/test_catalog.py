from app.catalog import Catalog
from app.models import MediaEntry


def test_catalog_replaces_entries_and_searches(tmp_path):
    db = tmp_path / "catalog.sqlite"
    catalog = Catalog(db)
    catalog.replace_entries([
        MediaEntry(title="Inception", url="http://example.test/inception.ts", kind="movie", group_title="Movies"),
        MediaEntry(title="The Show S01E01", url="http://example.test/s01e01.ts", kind="series", series_title="The Show", season=1, episode=1),
    ])

    results = catalog.search("show")

    assert len(results) == 1
    assert results[0].id is not None
    assert catalog.get(results[0].id).title == "The Show S01E01"
    assert results[0].season == 1


def test_catalog_import_tolerates_duplicate_urls(tmp_path):
    # Real M3U playlists repeat the same stream URL; the import must not abort.
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(title="Movie A", url="http://example.test/a.ts", kind="movie"),
        MediaEntry(title="Movie A (dup group)", url="http://example.test/a.ts", kind="movie"),
        MediaEntry(title="Movie B", url="http://example.test/b.ts", kind="movie"),
    ])

    results = catalog.search("")

    assert {r.url for r in results} == {
        "http://example.test/a.ts",
        "http://example.test/b.ts",
    }
    assert len(results) == 2


def test_catalog_groups_series_by_season(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(title="The Show S01E01", url="u1", kind="series", series_title="The Show", season=1, episode=1),
        MediaEntry(title="The Show S02E01", url="u2", kind="series", series_title="The Show", season=2, episode=1),
    ])

    grouped = catalog.series_tree()

    assert set(grouped["The Show"].keys()) == {1, 2}
    assert grouped["The Show"][1][0].episode == 1
    assert [entry.episode for entry in catalog.season_entries("The Show", 2)] == [1]
