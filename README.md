# HA Plex M3U Manager

Home Assistant add-on/web app to manage an authorized M3U catalogue and Plex library folders on Synology.

## Current status

A "video club" style library you browse like Netflix/Blockbuster and "rent"
(download) into your Plex folders on Synology:

- Imports the configured M3U URL into SQLite (sends a VLC user-agent so picky
  XUI.one providers return the real playlist instead of an HTML error page).
- Classifies entries into movies, series (grouped by show/season) and live
  channels (`SxxEyy` → series, EPG `tvg-id` → channel, otherwise movie).
- Poster-grid browsing with cover art from the playlist `tvg-logo`, served
  through a caching image proxy (fixes mixed-content and slow third-party hosts).
- Browse and filter by category/provider (Netflix, HBO, Anime, …), search,
  sort A–Z or by year, with pagination.
- Movie and series detail pages, optional TMDB review/synopsis/rating.
- "Rent" a movie, an episode, or a whole season; background download queue with
  live progress bars.
- Free/used/total space per folder; safe delete restricted to configured roots.
- Runs as a Home Assistant add-on with ingress (relative links via `<base>`).

## Reviews (optional)

Set a free [TMDB](https://www.themoviedb.org/settings/api) API key in the add-on
options (`tmdb_api_key`) to show synopsis and rating on detail pages. Without a
key everything else works; only the review block is hidden.

## Secrets

Do not commit playlist URLs or credentials. Use Home Assistant add-on options. The app masks sensitive query parameters such as `username`, `password`, and `token` when displaying the configured URL.

## Install in Home Assistant

1. Make sure the Synology SMB shares are mounted in Home Assistant as:
   - `/share/plex_movies`
   - `/share/plex_series`
2. In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
3. Add this repository URL:

   ```text
   https://github.com/ruipalm/ha-plex-m3u-manager
   ```

4. Install **Plex M3U Manager**.
5. Configure add-on options:

   ```yaml
   m3u_url: "https://your-authorized-playlist.example/list.m3u"
   movies_path: "/share/plex_movies"
   series_path: "/share/plex_series"
   ```

6. Start the add-on and open it from the Home Assistant sidebar/ingress.

## Local development

```bash
python3 -m pytest tests -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8099
```

## Repository layout

```text
repository.yaml              # Home Assistant add-on repository metadata
plex-m3u-manager/            # Home Assistant add-on
  config.yaml
  Dockerfile
  run.sh
  app/
app/                         # Development copy used by tests/local uvicorn
tests/
```
