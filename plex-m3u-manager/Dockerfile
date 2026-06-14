ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

WORKDIR /app
COPY app /app/app
COPY run.sh /run.sh
RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart httpx \
    && chmod a+x /run.sh

ENV MOVIES_PATH=/share/plex_movies
ENV SERIES_PATH=/share/plex_series
EXPOSE 8099
CMD ["/run.sh"]
