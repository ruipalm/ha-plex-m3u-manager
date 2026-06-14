from __future__ import annotations

from html import escape

from app.models import MediaEntry


def render_download_button(entry: MediaEntry) -> str:
    if entry.id is None:
        return ""
    return (
        "<form method='post' action='downloads' style='display:inline'>"
        f"<input type='hidden' name='entry_id' value='{entry.id}'>"
        "<button>Descarregar</button>"
        "</form>"
    )


def render_season_download_button(series_title: str, season: int) -> str:
    return (
        "<form method='post' action='downloads/season' style='display:inline'>"
        f"<input type='hidden' name='series_title' value='{escape(series_title, quote=True)}'>"
        f"<input type='hidden' name='season' value='{season}'>"
        "<button>Descarregar temporada</button>"
        "</form>"
    )
