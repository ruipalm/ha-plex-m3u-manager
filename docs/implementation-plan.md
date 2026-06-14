# Home Assistant M3U Plex Manager Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a Home Assistant add-on that imports an authorized M3U playlist, organizes movies and series, downloads selected media to Synology folders used by Plex, and manages available disk space.

**Architecture:** A Home Assistant add-on runs a FastAPI web app inside Home Assistant/Supervisor. The app stores only configuration/secrets in add-on options/environment, parses M3U entries into a local SQLite catalog, downloads selected streams to mounted Synology paths, and exposes a responsive UI suitable for HA sidebar/mobile use.

**Tech Stack:** Python 3.12, FastAPI, Jinja2/HTMX-style progressive UI, SQLite, pytest, Docker/Home Assistant add-on config.

---

## Security and compliance constraints

- Do not commit M3U URLs, usernames, passwords, tokens, or Synology credentials.
- M3U source must be authorized/licensed by the user.
- `.env`, add-on options, and runtime databases are ignored by git.
- Downloads are saved only to configured library paths.

## Home Assistant deployment target

Preferred deployment: Home Assistant add-on repository containing one add-on directory. The add-on exposes a web UI via ingress when possible, with optional direct port for local testing.

## Initial tasks

### Task 1: Project skeleton

**Objective:** Create Python package, tests, and HA add-on metadata.

**Files:**
- Create: `app/__init__.py`
- Create: `app/models.py`
- Create: `app/m3u.py`
- Create: `app/storage.py`
- Create: `app/main.py`
- Create: `tests/test_m3u.py`
- Create: `tests/test_storage.py`
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `homeassistant-addon/config.yaml`
- Create: `homeassistant-addon/Dockerfile`

### Task 2: M3U parser

**Objective:** Parse `#EXTINF` metadata, classify movies vs series, and keep stream URL opaque.

**Acceptance:** Tests cover movies, SxxEyy episodes, seasons, tvg-name, group-title, and fallback names.

### Task 3: Storage inspection

**Objective:** Report free/used/total bytes for the configured Movies and Series folders and list/delete files safely within those roots.

**Acceptance:** Tests prevent path traversal deletes and verify free-space formatting.

### Task 4: FastAPI MVP

**Objective:** Expose pages/API for catalog list, search, item detail, storage dashboard, and delete action.

**Acceptance:** `pytest` passes; local `uvicorn app.main:app` serves UI.

### Task 5: Download queue

**Objective:** Add background download jobs with progress, cancellation, and destination selection.

**Acceptance:** Tests cover filename sanitization, movie destination, series season/episode destination, duplicate handling, and low-space refusal.

### Task 6: HA add-on packaging

**Objective:** Package as a Home Assistant add-on with options for M3U URL, Movies path, Series path, and optional CIFS mount details.

**Acceptance:** Add-on builds and runs in HA; web UI reachable from HA sidebar/ingress.

### Task 7: Interface Goal cycles

**Objective:** Iterate UI in goal-driven passes: mobile-first search, bulk selection, season grouping, disk space visibility, destructive-action confirmation, download progress clarity.

**Acceptance:** Each cycle ends with screenshot/manual verification and a short note in `docs/ui-goals.md`.
