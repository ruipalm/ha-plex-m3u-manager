from app.m3u import classify_entry, looks_like_m3u, parse_m3u


def test_looks_like_m3u_accepts_playlist_and_rejects_html():
    assert looks_like_m3u("#EXTM3U\n#EXTINF:-1,Foo\nhttp://x/y.ts\n")
    assert looks_like_m3u("\n  #EXTINF:-1,Foo\nhttp://x/y.ts\n")
    assert not looks_like_m3u("<html><head><title>XUI.one - Debug Mode</title></head></html>")
    assert not looks_like_m3u("")


def test_parse_movie_entry_with_logo_and_year():
    text = """#EXTM3U\n#EXTINF:-1 tvg-id=\"\" tvg-name=\"Inception (2010)\" tvg-logo=\"http://img/i.jpg\" group-title=\"Netflix\",Inception (2010)\nhttp://example.test/movie.ts\n"""

    entries = parse_m3u(text)

    assert len(entries) == 1
    assert entries[0].title == "Inception (2010)"
    assert entries[0].kind == "movie"
    assert entries[0].year == 2010
    assert entries[0].logo == "http://img/i.jpg"
    assert entries[0].group_title == "Netflix"
    assert entries[0].url == "http://example.test/movie.ts"


def test_parse_series_episode_from_sxxeyy_name():
    text = """#EXTM3U\n#EXTINF:-1 tvg-name=\"The Show S02E03\" group-title=\"Series\",The Show S02E03\nhttp://example.test/ep.ts\n"""

    entry = parse_m3u(text)[0]

    assert entry.kind == "series"
    assert entry.series_title == "The Show"
    assert entry.season == 2
    assert entry.episode == 3


def test_classify_entry_with_epg_id_is_a_live_channel():
    entry = classify_entry({"group-title": "PT", "tvg-id": "RTP1.pt"}, "RTP1", "http://example.test/x.ts")

    assert entry.kind == "channel"


def test_classify_non_episode_vod_defaults_to_movie():
    entry = classify_entry({"group-title": "Netflix"}, "Some Film", "http://example.test/x.ts")

    assert entry.kind == "movie"
    assert entry.title == "Some Film"


def test_parser_uses_fallback_display_name_when_tvg_name_missing():
    text = """#EXTM3U\n#EXTINF:-1 group-title=\"Movies\",Fallback Name\nhttp://example.test/fallback.ts\n"""

    entry = parse_m3u(text)[0]

    assert entry.title == "Fallback Name"
