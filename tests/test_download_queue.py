import asyncio

import httpx
import pytest

from app.download_queue import DownloadQueue
from app.models import MediaEntry


class FakeResponse:
    def __init__(self, chunks, status_code=200, headers=None, fail_after=None, hang=False):
        self.chunks = chunks
        self.status_code = status_code
        self.headers = headers or {}
        self.fail_after = fail_after  # raise a connection drop after N chunks
        self.hang = hang  # never deliver data (simulates a stalled connection)

    def raise_for_status(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def aiter_bytes(self):
        if self.hang:
            await asyncio.sleep(3600)
        for i, chunk in enumerate(self.chunks):
            yield chunk
            if self.fail_after is not None and i + 1 >= self.fail_after:
                raise httpx.RemoteProtocolError("peer closed connection")


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def stream(self, method, url, headers=None):
        assert method == "GET"
        return FakeResponse([b"abc", b"def"], 200, {"content-length": "6"})


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
async def test_download_resumes_after_dropped_connection(tmp_path, monkeypatch):
    full = bytes(range(256)) * 8  # 2048 bytes
    drop_at = 700
    state = {"ranges": []}

    class ResumingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def stream(self, method, url, headers=None):
            rng = (headers or {}).get("Range")
            state["ranges"].append(rng)
            if rng is None:
                # First attempt: serve from the start, then drop mid-stream.
                return FakeResponse([full[:drop_at]], 200, {"content-length": str(len(full))}, fail_after=1)
            start = int(rng.split("=")[1].split("-")[0])
            return FakeResponse(
                [full[start:]], 206,
                {"content-range": f"bytes {start}-{len(full) - 1}/{len(full)}"},
            )

    monkeypatch.setattr(httpx, "AsyncClient", ResumingClient)
    queue = DownloadQueue(tmp_path / "movies", tmp_path / "series")
    queue.retry_backoff = 0  # no sleeping in tests
    entry = MediaEntry(title="Big", url="http://example.test/big.ts", kind="movie")

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert queue.get(job.id).status == "completed"
    assert (tmp_path / "movies" / "Big.ts").read_bytes() == full
    assert state["ranges"] == [None, f"bytes={drop_at}-"]  # resumed, not restarted


@pytest.mark.asyncio
async def test_download_recovers_from_a_stalled_connection(tmp_path, monkeypatch):
    payload = b"complete-payload"
    state = {"calls": 0}

    class StallThenOkClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def stream(self, method, url, headers=None):
            state["calls"] += 1
            if state["calls"] == 1:
                return FakeResponse([], 200, {"content-length": str(len(payload))}, hang=True)
            return FakeResponse([payload], 200, {"content-length": str(len(payload))})

    monkeypatch.setattr(httpx, "AsyncClient", StallThenOkClient)
    queue = DownloadQueue(tmp_path / "movies", tmp_path / "series")
    queue.stall_timeout = 0.05  # fire the watchdog fast
    queue.retry_backoff = 0
    entry = MediaEntry(title="Stall", url="http://example.test/s.ts", kind="movie")

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert queue.get(job.id).status == "completed"
    assert (tmp_path / "movies" / "Stall.ts").read_bytes() == payload
    assert state["calls"] == 2  # stalled once, then succeeded


@pytest.mark.asyncio
async def test_failed_series_download_keeps_partial_in_staging_tree(tmp_path, monkeypatch):
    class AlwaysDropClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def stream(self, method, url, headers=None):
            return FakeResponse([b"x"], 200, {"content-length": "100"}, fail_after=1)

    monkeypatch.setattr(httpx, "AsyncClient", AlwaysDropClient)
    queue = DownloadQueue(tmp_path / "movies", tmp_path / "series", max_retries=1)
    queue.retry_backoff = 0
    entry = MediaEntry(
        title="Episode 1",
        url="http://example.test/e1.ts",
        kind="series",
        series_title="Example Show",
        season=1,
        episode=1,
    )

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert queue.get(job.id).status == "failed"
    assert (tmp_path / "series" / ".downloads" / "Example Show" / "Season 01" / "Episode 1.ts.part").exists()
    assert not (tmp_path / "series" / "Example Show" / "Season 01" / "Episode 1.ts").exists()


@pytest.mark.asyncio
async def test_download_fails_after_exhausting_retries(tmp_path, monkeypatch):
    class AlwaysDropClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def stream(self, method, url, headers=None):
            return FakeResponse([b"x"], 200, {"content-length": "100"}, fail_after=1)

    monkeypatch.setattr(httpx, "AsyncClient", AlwaysDropClient)
    queue = DownloadQueue(tmp_path / "movies", tmp_path / "series", max_retries=3)
    queue.retry_backoff = 0
    entry = MediaEntry(title="Flaky", url="http://example.test/f.ts", kind="movie")

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert queue.get(job.id).status == "failed"
    # .part is kept in the staging directory so a later re-rent can resume
    # without Plex/SMB trying to index a partial file in the library root.
    assert (tmp_path / "movies" / ".downloads" / "Flaky.ts.part").exists()
    assert not (tmp_path / "movies" / "Flaky.ts").exists()


@pytest.mark.asyncio
async def test_download_queue_refuses_entry_without_protocol(tmp_path):
    queue = DownloadQueue(tmp_path / "movies", tmp_path / "series")
    entry = MediaEntry(title="html>", url="html", kind="movie")

    job = queue.enqueue(entry)
    await queue.run_job(job.id)

    assert queue.get(job.id).status == "failed"
    assert "no downloadable URL" in queue.get(job.id).error


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
