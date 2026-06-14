from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.catalog import Catalog
from app.config import load_config
from app.m3u import parse_m3u
from app.storage import delete_within_root, get_space_info, human_bytes, list_media_files

app = FastAPI(title="Home Assistant M3U Plex Manager")

CONFIG = load_config()
MOVIES_PATH = Path(CONFIG.movies_path)
SERIES_PATH = Path(CONFIG.series_path)
CATALOG = Catalog(CONFIG.database_path)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""
<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #101418; color: #eef2f5; }}
    header {{ padding: 1rem; background: #18212b; position: sticky; top: 0; }}
    main {{ padding: 1rem; display: grid; gap: 1rem; }}
    .card {{ background: #18212b; border: 1px solid #2c3a46; border-radius: 14px; padding: 1rem; }}
    a, button {{ color: #8bd3ff; }}
    input, textarea {{ width: 100%; box-sizing: border-box; padding: .7rem; border-radius: 10px; border: 1px solid #44515d; background: #0c1116; color: #eef2f5; }}
    button {{ background: #12324a; border: 1px solid #2d6f9f; border-radius: 10px; padding: .65rem .9rem; cursor: pointer; }}
    .danger {{ color: #ffb4b4; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header><strong>{title}</strong> · <a href="/">Início</a> · <a href="/storage">Espaço/Ficheiros</a></header>
  <main>{body}</main>
</body>
</html>
""")


@app.get("/", response_class=HTMLResponse)
def index():
    return _page("M3U Plex Manager", f"""
<div class="card">
  <h2>Importar M3U autorizado</h2>
  <p>URL configurado: <code>{CONFIG.masked_m3u_url() or 'não configurado'}</code></p>
  <form method="post" action="/import-url">
    <button type="submit">Importar do URL configurado</button>
  </form>
  <hr>
  <p>Ou cole conteúdo M3U manualmente para teste:</p>
  <form method="post" action="/preview">
    <textarea name="m3u_text" rows="12" placeholder="#EXTM3U..."></textarea><br><br>
    <button type="submit">Pré-visualizar catálogo</button>
  </form>
</div>
<div class="card">
  <h2>Catálogo</h2>
  <form method="get" action="/catalog">
    <input name="q" placeholder="Pesquisar filme ou série">
    <br><br><button type="submit">Pesquisar</button>
  </form>
  <p><a href="/series">Ver séries agrupadas por temporada</a></p>
</div>
""")


@app.post("/preview", response_class=HTMLResponse)
def preview(m3u_text: str = Form(...)):
    entries = parse_m3u(m3u_text)
    CATALOG.replace_entries(entries)
    movies = [entry for entry in entries if entry.kind == "movie"][:50]
    series = [entry for entry in entries if entry.kind == "series"][:50]
    body = [f"<div class='card'><h2>Resumo</h2><p>{len(entries)} entradas importadas e guardadas no catálogo. A mostrar até 50 filmes e 50 episódios.</p></div>"]
    body.append("<div class='grid'>")
    body.append("<section class='card'><h2>Filmes</h2><ul>" + "".join(f"<li>{m.title}</li>" for m in movies) + "</ul></section>")
    body.append("<section class='card'><h2>Séries</h2><ul>" + "".join(f"<li>{s.series_title or s.title} S{s.season or 0:02d}E{s.episode or 0:02d}</li>" for s in series) + "</ul></section>")
    body.append("</div>")
    return _page("Pré-visualização", "".join(body))


@app.post("/import-url")
def import_url():
    if not CONFIG.m3u_url:
        raise HTTPException(status_code=400, detail="M3U URL is not configured in add-on options")
    response = httpx.get(CONFIG.m3u_url, timeout=60)
    response.raise_for_status()
    CATALOG.replace_entries(parse_m3u(response.text))
    return RedirectResponse("/catalog", status_code=303)


@app.get("/catalog", response_class=HTMLResponse)
def catalog(q: str = ""):
    entries = CATALOG.search(q, limit=300)
    items = "".join(f"<li><strong>{entry.title}</strong> <small>{entry.kind}</small></li>" for entry in entries)
    return _page("Catálogo", f"<div class='card'><h2>Resultados</h2><form><input name='q' value='{q}' placeholder='Pesquisar'><br><br><button>Pesquisar</button></form><p>{len(entries)} entradas</p><ul>{items}</ul></div>")


@app.get("/series", response_class=HTMLResponse)
def series():
    tree = CATALOG.series_tree()
    parts = ["<div class='card'><h2>Séries</h2>"]
    for series_title, seasons in sorted(tree.items()):
        parts.append(f"<h3>{series_title}</h3>")
        for season, episodes in sorted(seasons.items()):
            parts.append(f"<details><summary>Season {season:02d} — {len(episodes)} episódios</summary><ul>")
            for episode in episodes:
                parts.append(f"<li>{episode.title}</li>")
            parts.append("</ul></details>")
    parts.append("</div>")
    return _page("Séries", "".join(parts))


@app.get("/storage", response_class=HTMLResponse)
def storage():
    sections = []
    for label, root in (("Filmes", MOVIES_PATH), ("Séries", SERIES_PATH)):
        info = get_space_info(root)
        files = list_media_files(root)[:200]
        sections.append(f"<section class='card'><h2>{label}</h2><p>Livre: <strong>{human_bytes(info.free_bytes)}</strong> / Total: {human_bytes(info.total_bytes)}</p><ul>")
        for media_file in files:
            sections.append(f"<li><code>{media_file.relative_path}</code> — {human_bytes(media_file.size_bytes)} <form method='post' action='/delete' style='display:inline' onsubmit=\"return confirm('Apagar este ficheiro?')\"><input type='hidden' name='root' value='{label}'><input type='hidden' name='path' value='{media_file.relative_path}'><button class='danger'>Apagar</button></form></li>")
        sections.append("</ul></section>")
    return _page("Espaço e ficheiros", "<div class='grid'>" + "".join(sections) + "</div>")


@app.post("/delete")
def delete_file(root: str = Form(...), path: str = Form(...)):
    target_root = MOVIES_PATH if root == "Filmes" else SERIES_PATH if root == "Séries" else None
    if target_root is None:
        raise HTTPException(status_code=400, detail="Invalid root")
    delete_within_root(target_root, path)
    return RedirectResponse("/storage", status_code=303)
