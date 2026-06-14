from __future__ import annotations

from math import ceil
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.catalog import Catalog
from app.config import load_config
from app.download_queue import DownloadQueue
from app.images import ImageCache
from app.m3u import filter_excluded, looks_like_m3u, parse_m3u
from app.storage import delete_within_root, get_space_info, human_bytes, list_media_files
from app.tmdb import Tmdb

app = FastAPI(title="Home Assistant M3U Plex Manager")

CONFIG = load_config()
MOVIES_PATH = Path(CONFIG.movies_path)
SERIES_PATH = Path(CONFIG.series_path)
CATALOG = Catalog(CONFIG.database_path)
DOWNLOADS = DownloadQueue(MOVIES_PATH, SERIES_PATH, user_agent=CONFIG.user_agent)
IMAGES = ImageCache(Path(CONFIG.cache_dir) / "img", user_agent=CONFIG.user_agent)
TMDB = Tmdb(CONFIG.tmdb_api_key, Path(CONFIG.cache_dir) / "tmdb", CONFIG.tmdb_language) if CONFIG.tmdb_api_key else None

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_STATUS_LABEL = {"queued": "Em fila", "running": "A descarregar", "completed": "Concluído", "failed": "Falhou"}


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    ctx.setdefault("title", "Videoclube")
    ctx["base"] = request.headers.get("X-Ingress-Path", "").rstrip("/")
    return templates.TemplateResponse(request, template, ctx)


def _active_jobs() -> int:
    return sum(1 for job in DOWNLOADS.all() if job.status in ("queued", "running"))


# -- home / import ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    counts = CATALOG.kind_counts()
    return _render(
        request, "index.html", nav="home",
        counts=counts, total=sum(counts.values()),
        categories=CATALOG.categories(), active_jobs=_active_jobs(),
        masked_url=CONFIG.masked_m3u_url(),
    )


@app.post("/import-url")
def import_url():
    if not CONFIG.m3u_url:
        raise HTTPException(status_code=400, detail="M3U URL is not configured in add-on options")
    response = httpx.get(
        CONFIG.m3u_url, timeout=120, follow_redirects=True,
        headers={"User-Agent": CONFIG.user_agent},
    )
    response.raise_for_status()
    if not looks_like_m3u(response.text):
        raise HTTPException(
            status_code=502,
            detail="The configured URL did not return an M3U playlist (the provider may have rejected the request). Check the URL and that the provider allows this client.",
        )
    entries = filter_excluded(parse_m3u(response.text), CONFIG.exclude_patterns)
    CATALOG.replace_entries(entries)
    return RedirectResponse("browse?type=movie", status_code=303)


# -- browse -----------------------------------------------------------------

@app.get("/browse", response_class=HTMLResponse)
def browse(request: Request, type: str = "movie", q: str = "", group: str = "", sort: str = "title", page: int = 1):
    type = "series" if type == "series" else "movie"
    group_filter = group or None
    page = max(page, 1)
    size = CONFIG.page_size
    offset = (page - 1) * size
    if type == "series":
        total = CATALOG.count_series(q, group_filter)
        items = CATALOG.list_series(q, group_filter, sort, size, offset)
    else:
        total = CATALOG.count_movies(q, group_filter)
        items = CATALOG.list_movies(q, group_filter, sort, size, offset)
    return _render(
        request, "browse.html", nav=type, type=type, q=q, group=group, sort=sort,
        items=items, total=total, page=page, pages=max(ceil(total / size), 1),
        categories=CATALOG.categories(type), search_type=type, refresh=0,
    )


@app.get("/categories", response_class=HTMLResponse)
def categories(request: Request, type: str = ""):
    kind = type if type in ("movie", "series") else None
    return _render(request, "categories.html", nav="categories", type=type, categories=CATALOG.categories(kind))


@app.get("/movie/{entry_id}", response_class=HTMLResponse)
def movie_detail(request: Request, entry_id: int):
    try:
        movie = CATALOG.get(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Movie not found")
    review = TMDB.lookup(movie.title, movie.year, "movie") if TMDB else None
    return _render(request, "movie.html", nav="movies", movie=movie, review=review, tmdb_enabled=bool(TMDB))


@app.get("/series/{name}", response_class=HTMLResponse)
def series_detail(request: Request, name: str):
    name = unquote(name)
    seasons = CATALOG.series_detail(name)
    if not seasons:
        raise HTTPException(status_code=404, detail="Series not found")
    first = next(iter(seasons.values()))[0]
    review = TMDB.lookup(name, first.year, "series") if TMDB else None
    return _render(
        request, "series.html", nav="series", name=name, seasons=seasons,
        total_episodes=sum(len(eps) for eps in seasons.values()),
        group_title=first.group_title, logo=first.logo, review=review,
    )


# -- downloads --------------------------------------------------------------

@app.get("/downloads", response_class=HTMLResponse)
def downloads(request: Request):
    jobs = []
    for job in reversed(DOWNLOADS.all()):
        percent = int(job.downloaded_bytes / job.total_bytes * 100) if job.total_bytes else 0
        jobs.append({
            "entry": job.entry, "status": job.status, "status_label": _STATUS_LABEL.get(job.status, job.status),
            "percent": percent, "downloaded_human": human_bytes(job.downloaded_bytes),
            "total_human": human_bytes(job.total_bytes) if job.total_bytes else "",
            "destination": str(job.destination), "error": job.error,
        })
    return _render(request, "downloads.html", nav="downloads", jobs=jobs, refresh=_active_jobs())


@app.post("/downloads")
def enqueue_download(background_tasks: BackgroundTasks, entry_id: int = Form(...)):
    try:
        entry = CATALOG.get(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found")
    job = DOWNLOADS.enqueue(entry)
    background_tasks.add_task(DOWNLOADS.run_job, job.id)
    return RedirectResponse("downloads", status_code=303)


@app.post("/downloads/season")
def enqueue_season_download(background_tasks: BackgroundTasks, series_title: str = Form(...), season: int = Form(...)):
    entries = CATALOG.season_entries(series_title, season)
    if not entries:
        raise HTTPException(status_code=404, detail="Season not found")
    for entry in entries:
        job = DOWNLOADS.enqueue(entry)
        background_tasks.add_task(DOWNLOADS.run_job, job.id)
    return RedirectResponse("downloads", status_code=303)


# -- storage ----------------------------------------------------------------

@app.get("/storage", response_class=HTMLResponse)
def storage(request: Request):
    sections = []
    for label, root in (("Filmes", MOVIES_PATH), ("Séries", SERIES_PATH)):
        info = get_space_info(root)
        files = list_media_files(root)[:200]
        used_pct = int(info.used_bytes / info.total_bytes * 100) if info.total_bytes else 0
        sections.append({
            "label": label, "free_human": human_bytes(info.free_bytes),
            "used_human": human_bytes(info.used_bytes), "total_human": human_bytes(info.total_bytes),
            "used_pct": used_pct,
            "files": [{"relative_path": f.relative_path, "size_human": human_bytes(f.size_bytes)} for f in files],
        })
    return _render(request, "storage.html", nav="storage", sections=sections)


@app.post("/delete")
def delete_file(root: str = Form(...), path: str = Form(...)):
    target_root = MOVIES_PATH if root == "Filmes" else SERIES_PATH if root == "Séries" else None
    if target_root is None:
        raise HTTPException(status_code=400, detail="Invalid root")
    delete_within_root(target_root, path)
    return RedirectResponse("storage", status_code=303)


# -- image proxy ------------------------------------------------------------

@app.get("/img")
def image_proxy(u: str):
    result = IMAGES.get(u)
    if result is None:
        raise HTTPException(status_code=404, detail="Image unavailable")
    content, content_type = result
    return Response(content, media_type=content_type, headers={"Cache-Control": "public, max-age=604800"})
