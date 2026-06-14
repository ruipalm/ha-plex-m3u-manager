from pathlib import Path

import pytest

from app.storage import delete_within_root, get_space_info, human_bytes, list_media_files


def test_human_bytes_formats_gibibytes():
    assert human_bytes(3 * 1024**3) == "3.0 GiB"


def test_get_space_info_returns_positive_values(tmp_path):
    info = get_space_info(tmp_path)

    assert info.total_bytes > 0
    assert info.free_bytes > 0
    assert info.used_bytes >= 0


def test_list_media_files_lists_relative_files(tmp_path):
    movie = tmp_path / "Movie.mkv"
    movie.write_text("demo")

    files = list_media_files(tmp_path)

    assert files[0].relative_path == "Movie.mkv"
    assert files[0].size_bytes == 4


def test_delete_within_root_deletes_child_file(tmp_path):
    target = tmp_path / "old.ts"
    target.write_text("x")

    delete_within_root(tmp_path, "old.ts")

    assert not target.exists()


def test_delete_within_root_rejects_path_traversal(tmp_path):
    outside = tmp_path.parent / "outside.ts"
    outside.write_text("x")

    with pytest.raises(ValueError):
        delete_within_root(tmp_path, "../outside.ts")

    assert outside.exists()
