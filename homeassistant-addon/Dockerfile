ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
RUN pip install --no-cache-dir fastapi 'uvicorn[standard]' jinja2 python-multipart httpx

ENV MOVIES_PATH=/share/plex/Movies
ENV SERIES_PATH=/share/plex/Series
EXPOSE 8099
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099"]
