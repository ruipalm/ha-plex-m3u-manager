from app.ui import render_download_button, render_season_download_button
from app.models import MediaEntry


def test_render_download_button_uses_catalog_id_not_stream_url():
    entry = MediaEntry(id=42, title="Movie", url="http://secret.example/movie.ts", kind="movie")

    html = render_download_button(entry)

    assert "entry_id" in html
    assert "42" in html
    assert "secret.example" not in html


def test_render_season_download_button_posts_series_and_season():
    html = render_season_download_button("The Show", 2)

    assert "series_title" in html
    assert "The Show" in html
    assert "season" in html
    assert "2" in html
