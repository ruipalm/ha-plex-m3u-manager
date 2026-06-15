from __future__ import annotations

import asyncio
import errno as _errno
import sqlite3
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


class _CancelledDownload(Exception):
    pass


@dataclass
class DownloadJob:
    id: str
    entry: MediaEntry
    destination: Path
    status: str = "queued"
    total_bytes: int | None = None
    downloaded_bytes: int = 0
    error: str = ""
    cancel_requested: bool = False


class DownloadQueue:
    def __init__(self, movies_root: str | Path, series_root: str | Path, user_agent: str | None = None,
                 max_retries: int = 6, history_path: str | Path | None = None):
        self.movies_root = Path(movies_root)
        self.series_root = Path(series_root)
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.retry_backoff = 2.0  # seconds; base for exponential backoff (0 in tests)
        self.stall_timeout = 90.0  # abort and resume if no chunk arrives within this
        self.history_path = Path(history_path) if history_path else None
        self._jobs: dict[str, DownloadJob] = {}
        self._semaphore: asyncio.Semaphore | None = None
        if self.history_path:
            self._init_history()
            self._load_history()

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(1)
        return self._semaphore

    # -- persistent history -------------------------------------------------

    def _connect_history(self) -> sqlite3.Connection:
        if self.history_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("Download history is not configured")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.history_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_history(self) -> None:
        with self._connect_history() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS download_jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    group_title TEXT,
                    tvg_name TEXT,
                    series_title TEXT,
                    season INTEGER,
                    episode INTEGER,
                    logo TEXT,
                    year INTEGER,
                    search_aliases TEXT,
                    entry_id INTEGER,
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_bytes INTEGER,
                    downloaded_bytes INTEGER NOT NULL,
                    error TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _load_history(self) -> None:
        with self._connect_history() as conn:
            rows = conn.execute("SELECT * FROM download_jobs ORDER BY created_at, rowid").fetchall()
        for row in rows:
            status = row["status"]
            error = row["error"] or ""
            # A process restart cannot resume an in-memory background task. Keep
            # it visible in history instead of pretending it is still active.
            if status in ("queued", "running"):
                status = "failed"
                error = error or "Interrompido pelo reinício do add-on"
            entry = MediaEntry(
                title=row["title"],
                url=row["url"],
                kind=row["kind"],
                group_title=row["group_title"],
                tvg_name=row["tvg_name"],
                series_title=row["series_title"],
                season=row["season"],
                episode=row["episode"],
                logo=row["logo"],
                year=row["year"],
                search_aliases=row["search_aliases"],
                id=row["entry_id"],
            )
            job = DownloadJob(
                id=row["id"],
                entry=entry,
                destination=Path(row["destination"]),
                status=status,
                total_bytes=row["total_bytes"],
                downloaded_bytes=row["downloaded_bytes"],
                error=error,
                cancel_requested=bool(row["cancel_requested"]),
            )
            self._jobs[job.id] = job
            if status != row["status"] or error != (row["error"] or ""):
                self._persist_job(job)

    def _persist_job(self, job: DownloadJob) -> None:
        if self.history_path is None:
            return
        with self._connect_history() as conn:
            conn.execute(
                """
                INSERT INTO download_jobs (
                    id, title, url, kind, group_title, tvg_name, series_title,
                    season, episode, logo, year, search_aliases, entry_id,
                    destination, status, total_bytes, downloaded_bytes, error,
                    cancel_requested, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    url=excluded.url,
                    kind=excluded.kind,
                    group_title=excluded.group_title,
                    tvg_name=excluded.tvg_name,
                    series_title=excluded.series_title,
                    season=excluded.season,
                    episode=excluded.episode,
                    logo=excluded.logo,
                    year=excluded.year,
                    search_aliases=excluded.search_aliases,
                    entry_id=excluded.entry_id,
                    destination=excluded.destination,
                    status=excluded.status,
                    total_bytes=excluded.total_bytes,
                    downloaded_bytes=excluded.downloaded_bytes,
                    error=excluded.error,
                    cancel_requested=excluded.cancel_requested,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    job.id,
                    job.entry.title,
                    job.entry.url,
                    job.entry.kind,
                    job.entry.group_title,
                    job.entry.tvg_name,
                    job.entry.series_title,
                    job.entry.season,
                    job.entry.episode,
                    job.entry.logo,
                    job.entry.year,
                    job.entry.search_aliases,
                    job.entry.id,
                    str(job.destination),
                    job.status,
                    job.total_bytes,
                    job.downloaded_bytes,
                    job.error,
                    int(job.cancel_requested),
                ),
            )

    # -- queue ---------------------------------------------------------------

    def enqueue(self, entry: MediaEntry) -> DownloadJob:
        dest = destination_for_entry(entry, self.movies_root, self.series_root)
        for existing in self._jobs.values():
            if existing.destination == dest and existing.status in ("queued", "running", "completed", "skipped"):
                return existing
        if dest.exists():
            size = dest.stat().st_size
            job = DownloadJob(
                id=uuid4().hex,
                entry=entry,
                destination=dest,
                status="skipped",
                total_bytes=size,
                downloaded_bytes=size,
                error="Já existe no destino",
            )
            self._jobs[job.id] = job
            self._persist_job(job)
            return job
        job = DownloadJob(id=uuid4().hex, entry=entry, destination=dest)
        self._jobs[job.id] = job
        self._persist_job(job)
        return job

    def get(self, job_id: str) -> DownloadJob:
        return self._jobs[job_id]

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in ("completed", "failed", "cancelled", "skipped"):
            return False
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
            job.error = ""
        self._persist_job(job)
        return True

    def all(self) -> list[DownloadJob]:
        return list(self._jobs.values())

    async def run_job(self, job_id: str) -> None:
        async with self._get_semaphore():
            await self._run_job_inner(job_id)

    async def _run_job_inner(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status in ("completed", "skipped"):
            self._persist_job(job)
            return
        if job.cancel_requested or job.status == "cancelled":
            job.status = "cancelled"
            job.error = ""
            self._persist_job(job)
            return
        if not job.entry.url.lower().startswith(("http://", "https://")):
            job.status = "failed"
            job.error = f"Entry has no downloadable URL: {job.entry.url!r}"
            self._persist_job(job)
            return
        if job.destination.exists():
            size = job.destination.stat().st_size
            job.status = "skipped"
            job.total_bytes = size
            job.downloaded_bytes = size
            job.error = "Já existe no destino"
            self._persist_job(job)
            return
        job.status = "running"
        self._persist_job(job)
        job.destination.parent.mkdir(parents=True, exist_ok=True)
        root = self.series_root if job.entry.kind == "series" else self.movies_root
        staging_dir = root / ".downloads"
        relative_destination = job.destination.relative_to(root)
        temp = staging_dir / relative_destination.with_name(relative_destination.name + ".part")
        temp.parent.mkdir(parents=True, exist_ok=True)
        # Resume across retries: the read timeout aborts a stalled connection so
        # we can reconnect with a Range header and continue where we left off.
        timeout = httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=None)

        try:
            for attempt in range(1, self.max_retries + 1):
                resume_from = temp.stat().st_size if temp.exists() else 0
                job.downloaded_bytes = resume_from
                self._persist_job(job)
                try:
                    await self._stream_once(job, temp, resume_from, timeout)
                except _CancelledDownload:
                    raise
                except _RETRYABLE as exc:
                    if attempt >= self.max_retries:
                        raise
                    job.error = f"Retomar ({attempt}/{self.max_retries}): {exc}"
                    self._persist_job(job)
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
            self._persist_job(job)
        except _CancelledDownload:
            job.status = "cancelled"
            job.error = ""
            self._persist_job(job)
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            job.status = "failed"
            job.error = str(exc)
            self._persist_job(job)
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
                self._persist_job(job)
                mode = "ab" if resume_from else "wb"
                fh = await _open_with_ebusy_retry(temp, mode)
                with fh:
                    chunks = response.aiter_bytes()
                    while True:
                        if job.cancel_requested:
                            raise _CancelledDownload()
                        # Hard stall watchdog: independent of httpx's own timeout,
                        # so a half-open/stalled connection can't hang the job.
                        try:
                            chunk = await asyncio.wait_for(chunks.__anext__(), timeout=self.stall_timeout)
                        except StopAsyncIteration:
                            break
                        if job.cancel_requested:
                            raise _CancelledDownload()
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
