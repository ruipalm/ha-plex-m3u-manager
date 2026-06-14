# HA Plex M3U Manager

Home Assistant add-on/web app to manage an authorized M3U catalogue and Plex library folders on Synology.

## Current status

MVP foundation:

- Parses M3U `#EXTINF` entries.
- Classifies movies and series episodes.
- Reads free/used/total space for configured folders.
- Lists media files.
- Deletes files safely only inside configured roots.
- Imports the configured M3U URL into SQLite.
- Provides catalogue search and series-by-season views.
- Provides a basic download queue.
- Downloads individual movies/episodes.
- Downloads complete seasons from the series view.
- Runs as a Home Assistant add-on with ingress.

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
