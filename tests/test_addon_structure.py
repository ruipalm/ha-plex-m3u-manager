from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "plex-m3u-manager"


def test_repository_yaml_exists_for_home_assistant_addon_repo():
    data = yaml.safe_load((ROOT / "repository.yaml").read_text())

    assert data["name"] == "HA Plex M3U Manager Add-ons"
    assert "url" in data


def test_addon_directory_contains_required_files():
    assert (ADDON / "config.yaml").exists()
    assert (ADDON / "Dockerfile").exists()
    assert (ADDON / "app" / "main.py").exists()


def test_addon_app_copy_stays_in_sync_with_development_app():
    ignored_dirs = {"__pycache__"}
    app_files = sorted(
        p.relative_to(ROOT / "app")
        for p in (ROOT / "app").rglob("*")
        if p.is_file() and not any(part in ignored_dirs for part in p.parts)
    )
    addon_files = sorted(
        p.relative_to(ADDON / "app")
        for p in (ADDON / "app").rglob("*")
        if p.is_file() and not any(part in ignored_dirs for part in p.parts)
    )

    assert addon_files == app_files
    for relative_path in app_files:
        assert (ADDON / "app" / relative_path).read_bytes() == (ROOT / "app" / relative_path).read_bytes()


def test_addon_uses_plain_python_image_without_s6_overlay():
    dockerfile = (ADDON / "Dockerfile").read_text()

    assert "FROM python:3.12-alpine" in dockerfile
    assert "with-contenv" not in dockerfile
    assert "bashio" not in dockerfile
    assert "services.d" not in dockerfile
    assert "CMD" in dockerfile
    assert "uvicorn" in dockerfile


def test_repository_has_no_stale_duplicate_addon_directory():
    assert not (ROOT / "homeassistant-addon").exists()


def test_only_one_addon_config_slug_exists():
    configs = [p for p in ROOT.glob("*/config.yaml") if p.parent.name != ".github"]
    slugs = []
    for config in configs:
        data = yaml.safe_load(config.read_text()) or {}
        if "slug" in data:
            slugs.append((config, data["slug"]))

    assert slugs == [(ADDON / "config.yaml", "plex_m3u_manager")]


def test_addon_config_uses_ingress_and_synology_share_defaults():
    data = yaml.safe_load((ADDON / "config.yaml").read_text())

    assert data["ingress"] is True
    assert data["ingress_port"] == 8099
    assert data["options"]["movies_path"] == "/share/plex_movies"
    assert data["options"]["series_path"] == "/share/plex_series"
    assert "share:rw" in data["map"]
