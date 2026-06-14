from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import httpx

from app.downloads import destination_for_entry
from app.models import MediaEntry


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
    def __init__(self, movies_root: str | Path, series_root: str | Path, user_agent: str | None = None):
        self.movies_root = Path(movies_root)
        self.series_root = Path(series_root)
        self.user_agent = user_agent
        self._jobs: dict[str, DownloadJob] = {}

    def enqueue(self, entry: MediaEntry) -> DownloadJob:
        job = DownloadJob(id=uuid4().hex, entry=entry, destination=destination_for_entry(entry, self.movies_root, self.series_root))
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
        temp_destination = job.destination.with_suffix(job.destination.suffix + ".part")
        headers = {"User-Agent": self.user_agent} if self.user_agent else None
        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True, headers=headers) as client:
                async with client.stream("GET", job.entry.url) as response:
                    response.raise_for_status()
                    if response.headers.get("content-length"):
                        job.total_bytes = int(response.headers["content-length"])
                    with temp_destination.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            output.write(chunk)
                            job.downloaded_bytes += len(chunk)
            temp_destination.rename(job.destination)
            job.status = "completed"
        except Exception as exc:  # pragma: no cover - defensive runtime path
            job.status = "failed"
            job.error = str(exc)
            if temp_destination.exists():
                temp_destination.unlink()
