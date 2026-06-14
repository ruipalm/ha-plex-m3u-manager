from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

# Posters in IPTV playlists are hosted on third-party domains, some over plain
# http. Serving them through the add-on (which is reached over https via ingress)
# avoids mixed-content blocking and keeps the browser from contacting those
# hosts directly. Fetched images are cached on disk to keep browsing snappy.


class ImageCache:
    def __init__(self, cache_dir: str | Path, user_agent: str | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent

    def _path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / digest

    def get(self, url: str) -> tuple[bytes, str] | None:
        """Return (bytes, content_type) for an http(s) image, or None on failure."""
        if not url.lower().startswith(("http://", "https://")):
            return None
        cached = self._path_for(url)
        meta = cached.with_suffix(".type")
        if cached.exists():
            content_type = meta.read_text().strip() if meta.exists() else "image/jpeg"
            return cached.read_bytes(), content_type
        headers = {"User-Agent": self.user_agent} if self.user_agent else None
        try:
            response = httpx.get(url, timeout=15, follow_redirects=True, headers=headers)
            response.raise_for_status()
        except Exception:
            return None
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"
        cached.write_bytes(response.content)
        meta.write_text(content_type)
        return response.content, content_type
