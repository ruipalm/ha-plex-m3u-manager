from app.downloads import destination_for_entry, sanitize_filename
from app.models import MediaEntry


def test_sanitize_filename_removes_path_separators_and_bad_chars():
    assert sanitize_filename("Bad/Movie: Name?") == "Bad Movie Name"


def test_movie_destination_uses_movies_root():
    entry = MediaEntry(title="Inception", url="http://example.test/inception.ts", kind="movie")

    dest = destination_for_entry(entry, "/movies", "/series")

    assert str(dest) == "/movies/Inception.ts"


def test_series_destination_uses_series_season_folder():
    entry = MediaEntry(
        title="The Show S02E03",
        url="http://example.test/ep.ts",
        kind="series",
        series_title="The Show",
        season=2,
        episode=3,
    )

    dest = destination_for_entry(entry, "/movies", "/series")

    assert str(dest) == "/series/The Show/Season 02/The Show S02E03.ts"
