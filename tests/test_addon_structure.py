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
    assert (ADDON / "build.yaml").exists()
    assert (ADDON / "Dockerfile").exists()
    assert (ADDON / "run.sh").exists()
    assert (ADDON / "app" / "main.py").exists()


def test_addon_build_yaml_has_arch_specific_base_images():
    data = yaml.safe_load((ADDON / "build.yaml").read_text())

    assert data["build_from"]["amd64"].endswith("amd64-base-python:3.12-alpine3.20")
    assert data["build_from"]["aarch64"].endswith("aarch64-base-python:3.12-alpine3.20")
    assert data["build_from"]["armv7"].endswith("armv7-base-python:3.12-alpine3.20")


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
