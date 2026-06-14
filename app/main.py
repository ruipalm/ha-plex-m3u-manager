from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.m3u import parse_m3u
from app.storage import delete_within_root, get_space_info, human_bytes, list_media_files

app = FastAPI(title="Home Assistant M3U Plex Manager")

MOVIES_PATH = Path(os.getenv("MOVIES_PATH", "/media/Movies"))
SERIES_PATH = Path(os.getenv("SERIES_PATH", "/media/Series"))


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
    return _page("M3U Plex Manager", """
<div class="card">
  <h2>Importar M3U autorizado</h2>
  <p>Cole o conteúdo M3U ou configure futuramente o URL nas opções do add-on. Não coloque credenciais no GitHub.</p>
  <form method="post" action="/preview">
    <textarea name="m3u_text" rows="12" placeholder="#EXTM3U..."></textarea><br><br>
    <button type="submit">Pré-visualizar catálogo</button>
  </form>
</div>
<div class="card">
  <h2>Próximos passos</h2>
  <p>O MVP atual valida parser, espaço e eliminação segura. A seguir entra fila de downloads e agrupamento por temporadas.</p>
</div>
""")


@app.post("/preview", response_class=HTMLResponse)
def preview(m3u_text: str = Form(...)):
    entries = parse_m3u(m3u_text)
    movies = [entry for entry in entries if entry.kind == "movie"][:50]
    series = [entry for entry in entries if entry.kind == "series"][:50]
    body = [f"<div class='card'><h2>Resumo</h2><p>{len(entries)} entradas importadas. A mostrar até 50 filmes e 50 episódios.</p></div>"]
    body.append("<div class='grid'>")
    body.append("<section class='card'><h2>Filmes</h2><ul>" + "".join(f"<li>{m.title}</li>" for m in movies) + "</ul></section>")
    body.append("<section class='card'><h2>Séries</h2><ul>" + "".join(f"<li>{s.series_title or s.title} S{s.season or 0:02d}E{s.episode or 0:02d}</li>" for s in series) + "</ul></section>")
    body.append("</div>")
    return _page("Pré-visualização", "".join(body))


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
