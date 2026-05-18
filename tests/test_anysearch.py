from __future__ import annotations

from types import SimpleNamespace


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeRequester:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {"results": []}
        self.exc = exc
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc:
            raise self.exc
        return FakeResponse(self.payload)


def test_anysearch_client_uses_anonymous_rest_and_parses_results():
    from kronos_fincept.web_search import AnySearchClient

    requester = FakeRequester(
        {
            "results": [
                {
                    "title": "Fed cuts odds rise",
                    "url": "https://example.com/fed",
                    "description": "Market prices shifted.",
                    "source": "news",
                    "published_at": "2026-05-18",
                }
            ]
        }
    )
    client = AnySearchClient(
        SimpleNamespace(enabled=True, endpoint="https://api.anysearch.com/v1/search", timeout_seconds=3, max_results=2),
        requester=requester,
    )

    response = client.search("Fed rate cut odds")

    assert response.status == "completed"
    assert response.provider == "anysearch"
    assert response.results[0].title == "Fed cuts odds rise"
    assert response.results[0].snippet == "Market prices shifted."
    url, kwargs = requester.calls[0]
    assert url == "https://api.anysearch.com/v1/search"
    assert kwargs["json"] == {"query": "Fed rate cut odds", "max_results": 2}
    assert "Authorization" not in kwargs.get("headers", {})


def test_anysearch_client_degrades_on_timeout():
    from kronos_fincept.web_search import AnySearchClient

    client = AnySearchClient(
        SimpleNamespace(enabled=True, endpoint="https://api.anysearch.com/v1/search", timeout_seconds=1, max_results=2),
        requester=FakeRequester(exc=TimeoutError("slow")),
    )

    response = client.search("gold macro")

    assert response.status == "failed"
    assert response.results == []
    assert "slow" in (response.error or "")
