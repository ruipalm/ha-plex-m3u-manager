import json

from app.config import AppConfig, load_config


def test_load_config_reads_home_assistant_options_file(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({
        "m3u_url": "http://example.test/list.m3u",
        "movies_path": "/share/plex_movies",
        "series_path": "/share/plex_series",
    }))

    cfg = load_config(options)

    assert cfg.m3u_url == "http://example.test/list.m3u"
    assert cfg.movies_path == "/share/plex_movies"
    assert cfg.series_path == "/share/plex_series"


def test_load_config_uses_safe_defaults_when_options_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("M3U_URL", raising=False)
    cfg = load_config(tmp_path / "missing.json")

    assert cfg.movies_path == "/share/plex_movies"
    assert cfg.series_path == "/share/plex_series"
    assert cfg.m3u_url == ""
    assert cfg.database_path == "runtime/catalog.sqlite"


def test_app_config_masks_secret_playlist_url():
    cfg = AppConfig(m3u_url="http://host/get.php?username=demo&token=secret", movies_path="/m", series_path="/s")

    assert cfg.masked_m3u_url() == "http://host/get.php?username=MASKED&token=MASKED"
