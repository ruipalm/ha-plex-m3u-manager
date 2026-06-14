from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
MAIN = ROOT / "app" / "main.py"


def test_templates_use_relative_paths_for_home_assistant_ingress():
    # Under ingress the app is served from a sub-path; every internal link must
    # be relative so the <base href> set from X-Ingress-Path resolves it.
    forbidden = ['href="/', "href='/", 'action="/', "action='/", 'src="/', "src='/"]
    for template in TEMPLATES.glob("*.html"):
        text = template.read_text()
        for token in forbidden:
            assert token not in text, f"{template.name} contains absolute path {token!r}"


def test_base_template_sets_ingress_base_href():
    assert '<base href="{{ base }}/">' in (TEMPLATES / "base.html").read_text()


def test_main_redirects_use_relative_paths():
    text = MAIN.read_text()
    assert 'RedirectResponse("/' not in text
    assert "RedirectResponse('/" not in text


def test_season_download_redirects_back_to_downloads_from_nested_route():
    text = MAIN.read_text()
    assert 'RedirectResponse("../downloads", status_code=303)' in text


def test_movie_card_links_by_id_not_stream_url():
    # The poster/detail links must not leak the opaque stream URL.
    macros = (TEMPLATES / "_macros.html").read_text()
    assert 'href="movie/{{ m.id }}"' in macros
    assert "m.url" not in macros
