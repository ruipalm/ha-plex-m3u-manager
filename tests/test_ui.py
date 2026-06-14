from pathlib import Path

from app.ui import render_download_button, render_season_download_button
from app.models import MediaEntry

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "plex-m3u-manager"


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


def test_ui_uses_relative_paths_for_home_assistant_ingress():
    main_py = (ADDON / "app" / "main.py").read_text()
    ui_py = (ADDON / "app" / "ui.py").read_text()
    combined = main_py + ui_py

    forbidden = [
        'href="/',
        "href='/",
        'action="/',
        "action='/",
        'RedirectResponse("/',
        "RedirectResponse('/",
    ]
    for token in forbidden:
        assert token not in combined

    assert 'href="storage"' in main_py
    assert 'action="catalog"' in main_py
    assert "action='downloads'" in ui_py
