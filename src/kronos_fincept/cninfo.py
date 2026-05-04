"""Official cninfo disclosure search adapter."""

from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from kronos_fincept.web_search import WebSearchResponse, WebSearchResult


_CNINFO_BASE_URL = "https://www.cninfo.com.cn/new"
_CNINFO_STATIC_BASE_URL = "https://static.cninfo.com.cn"
_DEFAULT_USER_AGENT = "KronosFinceptLab/10.2.4 (+https://github.com/DDDFXYqiming/KronosFinceptLab)"


class CninfoDisclosureClient:
    """Fetch official disclosure results from cninfo without extra config."""

    provider = "cninfo"

    def __init__(
        self,
        requester: Any | None = None,
        *,
        enabled: bool = True,
        timeout_seconds: int = 8,
        max_results: int = 4,
    ) -> None:
        self._requester = requester
        self._enabled = enabled
        try:
            self._timeout_seconds = max(1, int(timeout_seconds))
        except (TypeError, ValueError):
            self._timeout_seconds = 8
        try:
            self._max_results = max(1, min(8, int(max_results)))
        except (TypeError, ValueError):
            self._max_results = 4

    @property
    def is_configured(self) -> bool:
        return bool(self._enabled)

    def search(self, query: str) -> WebSearchResponse:
        started = time.perf_counter()
        clean_query = " ".join((query or "").split())
        if not clean_query:
            return self._response(False, "skipped", clean_query, started, [], "empty query")
        if not self.is_configured:
            return self._response(False, "disabled", clean_query, started, [], "cninfo disclosure provider is disabled")

        try:
            results = self._search_announcements(clean_query)
        except Exception as exc:
            return self._response(True, "failed", clean_query, started, [], _short_error(exc))

        status = "completed" if results else "skipped"
        error = None if results else "no results"
        return self._response(True, status, clean_query, started, results, error)

    def _search_announcements(self, query: str) -> list[WebSearchResult]:
        response = self._requests().get(
            f"{_CNINFO_BASE_URL}/fulltextSearch/full",
            params={
                "searchkey": query,
                "sdate": "",
                "edate": "",
                "isfulltext": "false",
                "sortName": "pubdate",
                "sortType": "desc",
                "pageNum": 1,
                "pageSize": self._max_results,
                "type": "",
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{_CNINFO_BASE_URL}/fulltextSearch?{urlencode({'keyWord': query})}",
                "User-Agent": _DEFAULT_USER_AGENT,
            },
            timeout=self._timeout_seconds,
        )
        payload = self._checked_json(response)
        announcements = payload.get("announcements") or []
        results: list[WebSearchResult] = []
        for item in announcements[: self._max_results]:
            if not isinstance(item, dict):
                continue
            title = _strip_html(item.get("announcementTitle") or item.get("shortTitle") or item.get("secName") or query)
            url = _announcement_url(item)
            if not title or not url:
                continue
            published_at = _published_at(item.get("announcementTime"))
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    snippet=_announcement_snippet(item, fallback_title=title, published_at=published_at),
                    source=self.provider,
                    published_at=published_at,
                )
            )
        return results

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
            raise RuntimeError("cninfo provider returned non-object JSON")
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
            provider=self.provider,
            query=query,
            results=results,
            elapsed_ms=int((time.perf_counter() - started_at) * 1000),
            error=error,
        )


def _announcement_url(item: dict[str, Any]) -> str | None:
    adjunct_url = _optional_str(item.get("adjunctUrl"))
    if adjunct_url:
        if adjunct_url.startswith("http://") or adjunct_url.startswith("https://"):
            return adjunct_url
        return f"{_CNINFO_STATIC_BASE_URL}/{adjunct_url.lstrip('/')}"

    announcement_id = _optional_str(item.get("announcementId"))
    org_id = _optional_str(item.get("orgId"))
    sec_code = _optional_str(item.get("secCode"))
    params = {
        "stockCode": sec_code,
        "announcementId": announcement_id,
        "orgId": org_id,
    }
    announcement_time = item.get("announcementTime")
    if announcement_time is not None:
        params["announcementTime"] = str(announcement_time)
    query = urlencode({key: value for key, value in params.items() if value})
    if not query:
        return None
    return f"{_CNINFO_BASE_URL}/disclosure/detail?{query}"


def _announcement_snippet(
    item: dict[str, Any],
    *,
    fallback_title: str,
    published_at: str | None,
) -> str:
    sec_name = _strip_html(item.get("secName") or "")
    short_title = _strip_html(item.get("shortTitle") or "")
    announcement_type = _strip_html(item.get("announcementTypeName") or "")
    parts = [part for part in (sec_name, short_title, announcement_type, published_at) if part]
    if parts:
        return " | ".join(parts)
    return fallback_title


def _published_at(value: Any) -> str | None:
    try:
        if value is None or value == "":
            return None
        dt = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _strip_html(value: Any) -> str:
    text = html.unescape(str(value or "").strip())
    return re.sub(r"<[^>]+>", "", text).strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _short_error(exc: BaseException, *, limit: int = 180) -> str:
    text = " ".join((str(exc).strip() or type(exc).__name__).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."

