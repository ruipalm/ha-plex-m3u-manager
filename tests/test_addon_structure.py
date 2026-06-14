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
    assert (ADDON / "run.sh").exists()
    assert (ADDON / "app" / "main.py").exists()


def test_addon_config_uses_ingress_and_synology_share_defaults():
    data = yaml.safe_load((ADDON / "config.yaml").read_text())

    assert data["ingress"] is True
    assert data["ingress_port"] == 8099
    assert data["options"]["movies_path"] == "/share/plex_movies"
    assert data["options"]["series_path"] == "/share/plex_series"
    assert "share:rw" in data["map"]
