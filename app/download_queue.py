from __future__ import annotations

import asyncio
import errno as _errno
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx

from app.downloads import destination_for_entry
from app.models import MediaEntry

# Errors worth retrying: IPTV VOD servers routinely drop long-running
# connections or stall mid-stream on big files.
_RETRYABLE = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    TimeoutError,  # raised by the stall watchdog (asyncio.wait_for)
)


async def _open_with_ebusy_retry(path: Path, mode: str, retries: int = 5) -> object:
    for attempt in range(retries):
        try:
            return path.open(mode)
        except OSError as exc:
            if exc.errno != _errno.EBUSY or attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
    return path.open(mode)  # unreachable, satisfies type checkers


@dataclass
class DownloadJob:
    id: str
    entry: MediaEntry
    destination: Path
    status: str = "queued"
    total_bytes: int | None = None
    downloaded_bytes: int = 0
    error: str = ""


class DownloadQueue:
    def __init__(self, movies_root: str | Path, series_root: str | Path, user_agent: str | None = None,
                 max_retries: int = 6):
        self.movies_root = Path(movies_root)
        self.series_root = Path(series_root)
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.retry_backoff = 2.0  # seconds; base for exponential backoff (0 in tests)
        self.stall_timeout = 90.0  # abort and resume if no chunk arrives within this
        self._jobs: dict[str, DownloadJob] = {}

    def enqueue(self, entry: MediaEntry) -> DownloadJob:
        dest = destination_for_entry(entry, self.movies_root, self.series_root)
        for existing in self._jobs.values():
            if existing.destination == dest and existing.status in ("queued", "running"):
                return existing
        job = DownloadJob(id=uuid4().hex, entry=entry, destination=dest)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> DownloadJob:
        return self._jobs[job_id]

    def all(self) -> list[DownloadJob]:
        return list(self._jobs.values())

    async def run_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job.entry.url.lower().startswith(("http://", "https://")):
            job.status = "failed"
            job.error = f"Entry has no downloadable URL: {job.entry.url!r}"
            return
        if job.destination.exists():
            job.status = "failed"
            job.error = f"Destination already exists: {job.destination}"
            return
        job.status = "running"
        job.destination.parent.mkdir(parents=True, exist_ok=True)
        temp = job.destination.with_suffix(job.destination.suffix + ".part")
        # Resume across retries: the read timeout aborts a stalled connection so
        # we can reconnect with a Range header and continue where we left off.
        timeout = httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=None)

        try:
            for attempt in range(1, self.max_retries + 1):
                resume_from = temp.stat().st_size if temp.exists() else 0
                job.downloaded_bytes = resume_from
                try:
                    await self._stream_once(job, temp, resume_from, timeout)
                except _RETRYABLE as exc:
                    if attempt >= self.max_retries:
                        raise
                    job.error = f"Retomar ({attempt}/{self.max_retries}): {exc}"
                    if self.retry_backoff:
                        await asyncio.sleep(min(self.retry_backoff ** attempt, 30))
                    continue
                else:
                    break

            if job.total_bytes and temp.stat().st_size < job.total_bytes:
                raise RuntimeError(
                    f"Incomplete download: {temp.stat().st_size} of {job.total_bytes} bytes"
                )
            temp.rename(job.destination)
            job.status = "completed"
            job.error = ""
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            job.status = "failed"
            job.error = str(exc)
            # Keep the .part file so re-renting can resume from where it stopped.

    async def _stream_once(self, job: DownloadJob, temp: Path, resume_from: int, timeout: httpx.Timeout) -> None:
        headers: dict[str, str] = {}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", job.entry.url, headers=headers) as response:
                response.raise_for_status()
                # If we asked to resume but the server ignored Range (200, not
                # 206), start over from the beginning.
                if resume_from and response.status_code != 206:
                    resume_from = 0
                    job.downloaded_bytes = 0
                job.total_bytes = _total_size(response.headers, resume_from)
                mode = "ab" if resume_from else "wb"
                fh = await _open_with_ebusy_retry(temp, mode)
                with fh:
                    chunks = response.aiter_bytes()
                    while True:
                        # Hard stall watchdog: independent of httpx's own timeout,
                        # so a half-open/stalled connection can't hang the job.
                        try:
                            chunk = await asyncio.wait_for(chunks.__anext__(), timeout=self.stall_timeout)
                        except StopAsyncIteration:
                            break
                        # Write off the event loop so a slow SMB share can't block it.
                        try:
                            await asyncio.to_thread(fh.write, chunk)
                        except OSError as exc:
                            if exc.errno == _errno.EBUSY:
                                raise httpx.ReadError(f"Resource busy during write: {exc}") from exc
                            raise
                        job.downloaded_bytes += len(chunk)


def _total_size(headers: httpx.Headers, resume_from: int) -> int | None:
    content_range = headers.get("content-range")
    if content_range and "/" in content_range:
        total = content_range.rsplit("/", 1)[-1].strip()
        if total.isdigit():
            return int(total)
    if headers.get("content-length"):
        return int(headers["content-length"]) + resume_from
    return None
