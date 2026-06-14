import httpx

from app.tmdb import Tmdb


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_tmdb_lookup_refreshes_stale_cache_without_original_title(tmp_path, monkeypatch):
    stale = Tmdb("key", tmp_path)._cache_path("series|Nos Meandros da Lei|None|pt-PT")
    stale.write_text('{"title":"Nos Meandros da Lei","overview":"","rating":null,"votes":null,"year":1997,"poster":null,"series_id":123}')

    def fake_get(url, params=None, timeout=None):
        return FakeResponse({
            "results": [{
                "id": 123,
                "name": "Nos Meandros da Lei",
                "original_name": "The Lincoln Lawyer",
                "first_air_date": "1997-03-04",
            }]
        })

    monkeypatch.setattr(httpx, "get", fake_get)

    review = Tmdb("key", tmp_path).lookup("Nos Meandros da Lei", None, "series")

    assert review is not None
    assert review.original_title == "The Lincoln Lawyer"


def test_tmdb_lookup_keeps_localized_and_original_titles(tmp_path, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert params["language"] == "pt-PT"
        return FakeResponse({
            "results": [{
                "id": 123,
                "name": "Nos Meandros da Lei",
                "original_name": "The Lincoln Lawyer",
                "overview": "Drama jurídico.",
                "vote_average": 8.1,
                "vote_count": 50,
                "first_air_date": "1997-03-04",
                "poster_path": "/poster.jpg",
            }]
        })

    monkeypatch.setattr(httpx, "get", fake_get)

    review = Tmdb("key", tmp_path).lookup("Nos Meandros da Lei", None, "series")

    assert review is not None
    assert review.title == "Nos Meandros da Lei"
    assert review.original_title == "The Lincoln Lawyer"
    assert set(review.search_aliases()) == {"Nos Meandros da Lei", "The Lincoln Lawyer"}
