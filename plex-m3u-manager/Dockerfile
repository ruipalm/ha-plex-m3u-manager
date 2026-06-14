FROM python:3.12-alpine

WORKDIR /app
COPY app /app/app
RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart httpx

ENV MOVIES_PATH=/share/plex_movies
ENV SERIES_PATH=/share/plex_series
EXPOSE 8099
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099"]
