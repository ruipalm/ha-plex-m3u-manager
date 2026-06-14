import asyncio

import httpx
import pytest

from app.download_queue import DownloadQueue
from app.models import MediaEntry


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = chunks
        self.headers = {"content-length": str(sum(len(chunk) for chunk in chunks))}

    def raise_for_status(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def stream(self, method, url):
        assert method == "GET"
        return FakeResponse([b"abc", b"def"])


@pytest.mark.asyncio
async def test_download_queue_downloads_movie_and_tracks_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    queue = DownloadQueue(tmp_path / "movies", tmp_path / "series")
    entry = MediaEntry(title="Movie", url="http://example.test/movie.ts", kind="movie")

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert (tmp_path / "movies" / "Movie.ts").read_bytes() == b"abcdef"
    assert queue.get(job.id).status == "completed"
    assert queue.get(job.id).downloaded_bytes == 6


@pytest.mark.asyncio
async def test_download_queue_refuses_duplicate_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    movies = tmp_path / "movies"
    movies.mkdir()
    (movies / "Movie.ts").write_text("existing")
    queue = DownloadQueue(movies, tmp_path / "series")
    entry = MediaEntry(title="Movie", url="http://example.test/movie.ts", kind="movie")

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert queue.get(job.id).status == "failed"
    assert "already exists" in queue.get(job.id).error
