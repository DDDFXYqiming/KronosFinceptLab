"""Generic web search provider adapters for agent research context."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from kronos_fincept.config import WebSearchConfig, settings


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str | None = None
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebSearchResponse:
    enabled: bool
    status: str
    provider: str | None
    query: str
    results: list[WebSearchResult]
    elapsed_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [item.to_dict() for item in self.results]
        return payload


class WebSearchClient:
    """Small HTTP-only search client.

    Supported providers are intentionally simple so the Zeabur single-container
    deployment does not need browser automation or heavy crawler dependencies.
    """

    def __init__(self, config: WebSearchConfig | Any | None = None, requester: Any | None = None) -> None:
        self.config = config or settings.web_search
        self._requester = requester

    @property
    def provider(self) -> str:
        return str(getattr(self.config, "provider", "") or "").strip().lower()

    @property
    def is_configured(self) -> bool:
        configured = getattr(self.config, "is_configured", None)
        if isinstance(configured, bool):
            return configured
        if callable(configured):
            return bool(configured())
        provider = self.provider
        if provider in {"", "none", "disabled", "off"}:
            return False
        if provider == "custom":
            return bool(getattr(self.config, "endpoint", ""))
        return bool(getattr(self.config, "api_key", ""))

    def search(self, query: str) -> WebSearchResponse:
        started = time.perf_counter()
        clean_query = " ".join((query or "").split())
        if not clean_query:
            return self._response(False, "skipped", clean_query, started, [], "empty query")
        if not self.is_configured:
            return self._response(False, "disabled", clean_query, started, [], "web search provider is not configured")

        try:
            if self.provider == "tavily":
                results = self._search_tavily(clean_query)
            elif self.provider == "brave":
                results = self._search_brave(clean_query)
            elif self.provider == "serper":
                results = self._search_serper(clean_query)
            elif self.provider == "custom":
                results = self._search_custom(clean_query)
            else:
                return self._response(True, "failed", clean_query, started, [], f"unsupported provider: {self.provider}")
        except Exception as exc:
            return self._response(True, "failed", clean_query, started, [], _short_error(exc))

        status = "completed" if results else "skipped"
        error = None if results else "no results"
        return self._response(True, status, clean_query, started, results, error)

    def _search_tavily(self, query: str) -> list[WebSearchResult]:
        response = self._requests().post(
            self._endpoint("https://api.tavily.com/search"),
            json={
                "api_key": getattr(self.config, "api_key", ""),
                "query": query,
                "search_depth": "basic",
                "max_results": self._max_results(),
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=self._timeout(),
        )
        return self._parse_results(self._checked_json(response).get("results") or [], provider="tavily")

    def _search_brave(self, query: str) -> list[WebSearchResult]:
        response = self._requests().get(
            self._endpoint("https://api.search.brave.com/res/v1/web/search"),
            params={"q": query, "count": self._max_results()},
            headers={"X-Subscription-Token": getattr(self.config, "api_key", "")},
            timeout=self._timeout(),
        )
        data = self._checked_json(response)
        return self._parse_results(((data.get("web") or {}).get("results") or []), provider="brave")

    def _search_serper(self, query: str) -> list[WebSearchResult]:
        response = self._requests().post(
            self._endpoint("https://google.serper.dev/search"),
            headers={"X-API-KEY": getattr(self.config, "api_key", ""), "Content-Type": "application/json"},
            json={"q": query, "num": self._max_results()},
            timeout=self._timeout(),
        )
        return self._parse_results(self._checked_json(response).get("organic") or [], provider="serper")

    def _search_custom(self, query: str) -> list[WebSearchResult]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = getattr(self.config, "api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = self._requests().post(
            self._endpoint(""),
            headers=headers,
            json={"query": query, "max_results": self._max_results()},
            timeout=self._timeout(),
        )
        data = self._checked_json(response)
        raw_results = data.get("results") or data.get("items") or data.get("organic") or []
        return self._parse_results(raw_results, provider="custom")

    def _parse_results(self, raw_results: list[Any], *, provider: str) -> list[WebSearchResult]:
        results: list[WebSearchResult] = []
        for item in raw_results[: self._max_results()]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            url = str(item.get("url") or item.get("link") or "").strip()
            snippet = str(item.get("snippet") or item.get("content") or item.get("description") or "").strip()
            if not title or not url:
                continue
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source=str(item.get("source") or provider),
                    published_at=_optional_str(item.get("published_date") or item.get("published_at") or item.get("date")),
                )
            )
        return results

    def _endpoint(self, default: str) -> str:
        return str(getattr(self.config, "endpoint", "") or default).rstrip("/")

    def _timeout(self) -> int:
        try:
            return max(1, int(getattr(self.config, "timeout_seconds", 8)))
        except (TypeError, ValueError):
            return 8

    def _max_results(self) -> int:
        try:
            return max(1, min(8, int(getattr(self.config, "max_results", 4))))
        except (TypeError, ValueError):
            return 4

    def _requests(self) -> Any:
        if self._requester is not None:
            return self._requester
        import requests

        return requests

    def _checked_json(self, response: Any) -> dict[str, Any]:
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        status_code = getattr(response, "status_code", 200)
        if int(status_code) >= 400:
            raise RuntimeError(f"HTTP {status_code}")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("search provider returned non-object JSON")
        return data

    def _response(
        self,
        enabled: bool,
        status: str,
        query: str,
        started_at: float,
        results: list[WebSearchResult],
        error: str | None,
    ) -> WebSearchResponse:
        return WebSearchResponse(
            enabled=enabled,
            status=status,
            provider=self.provider or None,
            query=query,
            results=results,
            elapsed_ms=int((time.perf_counter() - started_at) * 1000),
            error=error,
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _short_error(exc: BaseException, *, limit: int = 180) -> str:
    text = " ".join((str(exc).strip() or type(exc).__name__).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
