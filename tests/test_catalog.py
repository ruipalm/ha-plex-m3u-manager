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


def test_catalog_search_matches_tmdb_aliases(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(
            title="Nos Meandros da Lei S01E01",
            url="s1",
            kind="series",
            series_title="Nos Meandros da Lei",
            season=1,
            episode=1,
            search_aliases="The Practice",
        ),
        MediaEntry(title="Outro", url="m1", kind="movie"),
    ])

    series = catalog.list_series(query="practice")
    raw = catalog.search("practice", kind="series")

    assert [s.series_title for s in series] == ["Nos Meandros da Lei"]
    assert [e.title for e in raw] == ["Nos Meandros da Lei S01E01"]


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


def test_catalog_lists_movies_and_series_with_categories(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(title="Heat (1995)", url="m1", kind="movie", group_title="Netflix", year=1995, logo="l1"),
        MediaEntry(title="Dune (2021)", url="m2", kind="movie", group_title="Prime", year=2021, logo="l2"),
        MediaEntry(title="The Show S01E01", url="s1", kind="series", series_title="The Show", season=1, episode=1, group_title="HBO", logo="ls"),
        MediaEntry(title="The Show S01E02", url="s2", kind="series", series_title="The Show", season=1, episode=2, group_title="HBO", logo="ls"),
        MediaEntry(title="RTP1", url="c1", kind="channel", group_title="PT"),
    ])

    assert catalog.count_movies() == 2
    assert catalog.count_series() == 1  # grouped by series, not episodes
    series = catalog.list_series()
    assert series[0].series_title == "The Show"
    assert series[0].episodes == 2 and series[0].seasons == 1

    # categories are scoped by kind
    movie_cats = {c.name for c in catalog.categories("movie")}
    assert movie_cats == {"Netflix", "Prime"}

    by_year = catalog.list_movies(sort="year")
    assert [m.title for m in by_year] == ["Dune (2021)", "Heat (1995)"]

    filtered = catalog.list_movies(group="Netflix")
    assert len(filtered) == 1 and filtered[0].title == "Heat (1995)"


def test_catalog_series_detail_groups_by_season(tmp_path):
    catalog = Catalog(tmp_path / "catalog.sqlite")
    catalog.replace_entries([
        MediaEntry(title="X S01E01", url="a", kind="series", series_title="X", season=1, episode=1),
        MediaEntry(title="X S02E01", url="b", kind="series", series_title="X", season=2, episode=1),
    ])

    detail = catalog.series_detail("X")
    assert set(detail.keys()) == {1, 2}


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
