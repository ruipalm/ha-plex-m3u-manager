#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Plex M3U Manager"
exec uvicorn app.main:app --host 0.0.0.0 --port 8099
