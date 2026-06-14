# HA Plex M3U Manager

Home Assistant add-on/web app to manage an authorized M3U catalogue and Plex library folders on Synology.

## Current status

MVP foundation:

- Parses M3U `#EXTINF` entries.
- Classifies movies and series episodes.
- Reads free/used/total space for configured folders.
- Lists media files.
- Deletes files safely only inside configured roots.
- Provides a basic FastAPI UI.

## Secrets

Do not commit playlist URLs or credentials. Use Home Assistant add-on options or a local `.env` file ignored by git.

## Local development

```bash
python3 -m pytest tests -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8099
```

## Home Assistant target

The intended deployment is a Home Assistant add-on with ingress. The Synology folders should be mounted into Home Assistant under `/share/plex/Movies` and `/share/plex/Series`, or paths adjusted in add-on options.
