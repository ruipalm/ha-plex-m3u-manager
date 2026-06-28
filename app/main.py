from __future__ import annotations

import re
from math import ceil
from pathlib import Path
from urllib.parse import unquote, urlencode

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
DOWNLOADS = DownloadQueue(
    MOVIES_PATH,
    SERIES_PATH,
    user_agent=CONFIG.user_agent,
    history_path=Path(CONFIG.database_path).with_name("downloads.sqlite"),
)
IMAGES = ImageCache(Path(CONFIG.cache_dir) / "img", user_agent=CONFIG.user_agent)
TMDB = Tmdb(CONFIG.tmdb_api_key, Path(CONFIG.cache_dir) / "tmdb", CONFIG.tmdb_language) if CONFIG.tmdb_api_key else None

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_STATUS_LABEL = {"queued": "Em fila", "running": "A descarregar", "completed": "Concluído", "failed": "Falhou", "cancelled": "Cancelado", "skipped": "Já existe"}
_ALIAS_REFRESH = {"running": False, "checked": 0, "updated": 0, "misses": 0, "error": ""}
_TOP_FETCH: dict[str, object] = {"running": False, "kind": "", "done": 0, "total": 0, "error": ""}


def _refresh_tmdb_aliases(catalog: Catalog, tmdb: Tmdb | None, limit: int | None = None) -> dict[str, int]:
    stats = {"checked": 0, "updated": 0, "misses": 0}
    if tmdb is None:
        return stats
    for target in catalog.tmdb_alias_targets(limit=limit):
        kind = str(target["kind"])
        title = str(target["title"])
        year = target["year"] if isinstance(target["year"], int) else None
        stats["checked"] += 1
        review = tmdb.lookup(title, year, kind)
        if not review:
            stats["misses"] += 1
            continue
        aliases = review.search_aliases()
        catalog.update_search_aliases(kind, title, aliases)
        stats["updated"] += 1
    return stats


def _run_alias_refresh() -> None:
    _ALIAS_REFRESH.update({"running": True, "checked": 0, "updated": 0, "misses": 0, "error": ""})
    try:
        stats = _refresh_tmdb_aliases(CATALOG, TMDB)
        _ALIAS_REFRESH.update(stats)
    except Exception as exc:  # noqa: BLE001 - surface background errors in UI
        _ALIAS_REFRESH["error"] = str(exc)
    finally:
        _ALIAS_REFRESH["running"] = False


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
        masked_url=CONFIG.masked_m3u_url(), tmdb_enabled=bool(TMDB), alias_refresh=_ALIAS_REFRESH,
        refresh=1 if _ALIAS_REFRESH.get("running") else 0,
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


@app.post("/tmdb/aliases")
def refresh_tmdb_aliases(background_tasks: BackgroundTasks):
    if not TMDB:
        _ALIAS_REFRESH.update({"running": False, "checked": 0, "updated": 0, "misses": 0, "error": "TMDB não está configurado"})
        return RedirectResponse("", status_code=303)
    if not _ALIAS_REFRESH.get("running"):
        background_tasks.add_task(_run_alias_refresh)
    return RedirectResponse("", status_code=303)


# -- browse -----------------------------------------------------------------

@app.get("/browse", response_class=HTMLResponse)
def browse(request: Request, type: str = "movie", q: str = "", group: str = "", sort: str = "title", page: int = 1, invert: str = ""):
    type = "series" if type == "series" else "movie"
    group_filter = group or None
    invert_filter = invert in ("1", "true", "on")
    page = max(page, 1)
    size = CONFIG.page_size
    offset = (page - 1) * size
    if type == "series":
        total = CATALOG.count_series(q, group_filter, invert_filter)
        items = CATALOG.list_series(q, group_filter, sort, size, offset, invert_filter)
    else:
        total = CATALOG.count_movies(q, group_filter, invert_filter)
        items = CATALOG.list_movies(q, group_filter, sort, size, offset, invert_filter)
    pages = max(ceil(total / size), 1)
    start_page = max(1, page - 2)
    end_page = min(pages, page + 2)
    page_numbers = list(range(start_page, end_page + 1))

    def page_url(target_page: int) -> str:
        params = {"type": type, "q": q, "group": group, "sort": sort, "page": target_page}
        if invert_filter:
            params["invert"] = "1"
        return urlencode(params)

    return _render(
        request, "browse.html", nav=type, type=type, q=q, group=group, sort=sort, invert=invert_filter,
        items=items, total=total, page=page, pages=pages, page_numbers=page_numbers, page_url=page_url,
        categories=CATALOG.categories(type), search_type=type, refresh=0,
    )


_EPISODE_CODE_RE = re.compile(r"^S\d{1,2}E\d{1,3}", re.IGNORECASE)
_TOP_MIN_VOTES = 50     # below this → unrated bucket
_TOP_MEAN_RATING = 7.0  # Bayesian prior (TMDB global average)


def _bayesian_score(review) -> float:
    """IMDb-style weighted rating: WR = (v/(v+m))*R + (m/(v+m))*C"""
    v = review.votes or 0
    r = review.rating or 0.0
    m = _TOP_MIN_VOTES
    return (v / (v + m)) * r + (m / (v + m)) * _TOP_MEAN_RATING


def _run_top_fetch(kind: str) -> None:
    """Background task: fetch TMDB data for all uncached items of the given kind."""
    if TMDB is None:
        return
    targets = CATALOG.tmdb_alias_targets()
    targets = [t for t in targets if t["kind"] == kind]
    _TOP_FETCH.update({"running": True, "kind": kind, "done": 0, "total": len(targets), "error": ""})
    try:
        for t in targets:
            title = str(t["title"])
            if _EPISODE_CODE_RE.match(title):
                _TOP_FETCH["done"] = int(_TOP_FETCH["done"]) + 1  # type: ignore[assignment]
                continue
            year = t["year"] if isinstance(t["year"], int) else None
            # lookup() uses disk cache when available → only makes HTTP for uncached items
            try:
                TMDB.lookup(title, year, kind)
            except Exception:
                pass
            _TOP_FETCH["done"] = int(_TOP_FETCH["done"]) + 1  # type: ignore[assignment]
    except Exception as exc:
        _TOP_FETCH["error"] = str(exc)
    finally:
        _TOP_FETCH["running"] = False


@app.get("/top", response_class=HTMLResponse)
def top(request: Request, background_tasks: BackgroundTasks, type: str = "series", group: str = ""):
    kind = "series" if type != "movie" else "movie"
    group_filter = group or None

    if kind == "series":
        items = CATALOG.list_series(query="", group=group_filter, sort="title", limit=5000, offset=0)
    else:
        items = CATALOG.list_movies(query="", group=group_filter, sort="title", limit=5000, offset=0)

    rated: list[dict] = []
    unrated: list[dict] = []
    for it in items:
        title = it.series_title if kind == "series" else it.title
        # Skip entries whose title is just an episode code (misclassified series episodes)
        if _EPISODE_CODE_RE.match(title or ""):
            continue
        review = TMDB.lookup_cached(title, it.year, kind) if TMDB else None
        row = {"item": it, "review": review, "score": 0.0}
        if review and review.rating and (review.votes or 0) >= _TOP_MIN_VOTES:
            row["score"] = _bayesian_score(review)
            rated.append(row)
        else:
            unrated.append(row)

    rated.sort(key=lambda r: (-r["score"], (r["item"].series_title if kind == "series" else r["item"].title).lower()))
    unrated.sort(key=lambda r: (r["item"].series_title if kind == "series" else r["item"].title).lower())

    # Auto-fetch TMDB data in background when most items are unrated
    fetch_running = bool(_TOP_FETCH.get("running")) and _TOP_FETCH.get("kind") == kind
    total_items = len(rated) + len(unrated)
    if TMDB and not fetch_running and len(rated) < total_items * 0.5:
        background_tasks.add_task(_run_top_fetch, kind)
        fetch_running = True

    fetch_done = int(_TOP_FETCH.get("done", 0))
    fetch_total = int(_TOP_FETCH.get("total", 0))

    return _render(
        request, "top.html",
        nav="top",
        type=kind,
        group=group,
        rows=rated + unrated,
        rated_count=len(rated),
        categories=CATALOG.categories(kind),
        tmdb_enabled=bool(TMDB),
        fetch_running=fetch_running,
        fetch_done=fetch_done,
        fetch_total=fetch_total,
        refresh=4 if fetch_running else 0,
    )


@app.get("/categories", response_class=HTMLResponse)
def categories(request: Request, type: str = "movie"):
    kind = type if type in ("movie", "series") else "movie"
    return _render(request, "categories.html", nav="categories", type=kind, categories=CATALOG.categories(kind))


@app.get("/movie/{entry_id}", response_class=HTMLResponse)
def movie_detail(request: Request, entry_id: int):
    try:
        movie = CATALOG.get(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Movie not found")
    review = TMDB.lookup(movie.title, movie.year, "movie") if TMDB else None
    if review:
        CATALOG.update_search_aliases("movie", movie.title, review.search_aliases())
    return _render(request, "movie.html", nav="movies", movie=movie, review=review, tmdb_enabled=bool(TMDB))


@app.get("/series/{name}", response_class=HTMLResponse)
def series_detail(request: Request, name: str):
    name = unquote(name)
    seasons = CATALOG.series_detail(name)
    if not seasons:
        raise HTTPException(status_code=404, detail="Series not found")
    first = next(iter(seasons.values()))[0]
    review = TMDB.lookup(name, first.year, "series") if TMDB else None
    if review:
        CATALOG.update_search_aliases("series", name, review.search_aliases())
    tmdb_episodes: dict[int, dict[int, object]] = {}
    if TMDB and review and review.series_id:
        for season_num in seasons:
            eps = TMDB.season_episodes(review.series_id, season_num)
            if eps:
                tmdb_episodes[season_num] = eps
    return _render(
        request, "series.html", nav="series", name=name, seasons=seasons,
        total_episodes=sum(len(eps) for eps in seasons.values()),
        group_title=first.group_title, logo=first.logo, review=review,
        tmdb_episodes=tmdb_episodes,
    )


# -- downloads --------------------------------------------------------------

@app.get("/downloads", response_class=HTMLResponse)
def downloads(request: Request):
    jobs = []
    for job in reversed(DOWNLOADS.all()):
        percent = int(job.downloaded_bytes / job.total_bytes * 100) if job.total_bytes else 0
        jobs.append({
            "id": job.id,
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
    if job.status == "queued":
        background_tasks.add_task(DOWNLOADS.run_job, job.id)
    return RedirectResponse("downloads", status_code=303)


@app.post("/downloads/season")
def enqueue_season_download(background_tasks: BackgroundTasks, series_title: str = Form(...), season: int = Form(...)):
    entries = CATALOG.season_entries(series_title, season)
    if not entries:
        raise HTTPException(status_code=404, detail="Season not found")
    for entry in entries:
        job = DOWNLOADS.enqueue(entry)
        if job.status == "queued":
            background_tasks.add_task(DOWNLOADS.run_job, job.id)
    return RedirectResponse("../downloads", status_code=303)


@app.post("/downloads/cancel")
def cancel_download(job_id: str = Form(...)):
    DOWNLOADS.cancel(job_id)
    return RedirectResponse("../downloads", status_code=303)


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


# -- debug ------------------------------------------------------------------

@app.get("/debug/series/{name}")
def debug_series(name: str):
    from urllib.parse import unquote as _unquote
    name = _unquote(name)
    seasons = CATALOG.series_detail(name)
    first_ep = next(iter(seasons.values()), [])[0] if seasons else None
    review = TMDB.lookup(name, first_ep.year if first_ep else None, "series") if TMDB else None
    eps_per_season = {}
    if TMDB and review and review.series_id:
        for s in seasons:
            eps = TMDB.season_episodes(review.series_id, s)
            eps_per_season[s] = {k: v.__dict__ for k, v in eps.items()}
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "series": name,
        "review_title": review.title if review else None,
        "series_id": review.series_id if review else None,
        "seasons_in_catalog": list(seasons.keys()),
        "tmdb_episodes_count": {s: len(e) for s, e in eps_per_season.items()},
        "sample": {str(s): {str(k): v["name"] for k, v in list(e.items())[:3]} for s, e in eps_per_season.items()},
    })


# -- image proxy ------------------------------------------------------------

@app.get("/img")
def image_proxy(u: str):
    result = IMAGES.get(u)
    if result is None:
        raise HTTPException(status_code=404, detail="Image unavailable")
    content, content_type = result
    return Response(content, media_type=content_type, headers={"Cache-Control": "public, max-age=604800"})
