"""POST /api/news/rss -- Fetch and normalize RSS/Atom feeds."""

from __future__ import annotations

import asyncio
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from kronos_fincept.security_utils import validate_public_https_url


router = APIRouter()

_MAX_FEEDS = 12
_MAX_LIMIT_PER_FEED = 20
_MAX_FEED_BYTES = 1_000_000
_HTTP_USER_AGENT = "KronosFinceptLab/10.9 RSS Reader"
DEFAULT_RSS_FEEDS: tuple[dict[str, str], ...] = (
    {"id": "fed", "title": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"id": "sec", "title": "SEC", "url": "https://www.sec.gov/news/pressreleases.rss"},
    {"id": "ecb", "title": "ECB", "url": "https://www.ecb.europa.eu/rss/press.html"},
)


class RssFeedIn(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=120)
    url: str = Field(..., min_length=8, max_length=500)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return validate_public_https_url(value, dns_env_key="KRONOS_RSS_VALIDATE_DNS")


class RssFetchRequest(BaseModel):
    feeds: list[RssFeedIn] = Field(..., min_length=1, max_length=_MAX_FEEDS)
    limit_per_feed: int = Field(default=8, ge=1, le=_MAX_LIMIT_PER_FEED)


class RssItemOut(BaseModel):
    feed_id: str
    feed_title: str
    title: str
    url: str
    published_at: str | None = None
    summary: str | None = None


class RssFetchResponse(BaseModel):
    ok: bool
    items: list[RssItemOut]
    errors: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class _Feed:
    id: str
    title: str
    url: str


@router.post("/news/rss", response_model=RssFetchResponse)
async def fetch_rss(req: RssFetchRequest) -> RssFetchResponse:
    items: list[RssItemOut] = []
    errors: dict[str, str] = {}
    for index, feed in enumerate(req.feeds):
        normalized = _normalize_feed(feed, index)
        try:
            text = await asyncio.to_thread(_fetch_text, normalized.url)
            items.extend(_parse_feed(normalized, text, req.limit_per_feed))
        except Exception as exc:
            errors[normalized.id] = _short_error(exc)
    return RssFetchResponse(ok=bool(items) or not errors, items=items, errors=errors)


def _normalize_feed(feed: RssFeedIn, index: int) -> _Feed:
    feed_id = (feed.id or feed.title or f"feed-{index + 1}").strip()[:80]
    title = (feed.title or feed_id).strip()[:120]
    return _Feed(id=feed_id, title=title, url=feed.url)


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
            "User-Agent": _HTTP_USER_AGENT,
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(_MAX_FEED_BYTES + 1)
    if len(raw) > _MAX_FEED_BYTES:
        raise ValueError("feed response is too large")
    return raw.decode("utf-8", errors="replace")


def _parse_feed(feed: _Feed, text: str, limit: int) -> list[RssItemOut]:
    root = ET.fromstring(text)
    if _local_name(root.tag) == "feed":
        return _parse_atom(feed, root, limit)
    channel = root.find("channel")
    if channel is None:
        channel = root
    return _parse_rss(feed, channel, limit)


def _parse_rss(feed: _Feed, channel: ET.Element, limit: int) -> list[RssItemOut]:
    items: list[RssItemOut] = []
    feed_title = _text(channel.find("title")) or feed.title
    for item in channel.findall("item")[:limit]:
        title = _clean_text(_text(item.find("title")) or "Untitled")
        url = _safe_item_url(_text(item.find("link")) or _guid_link(item))
        if not url:
            continue
        items.append(
            RssItemOut(
                feed_id=feed.id,
                feed_title=feed_title,
                title=title,
                url=url,
                published_at=_text(item.find("pubDate")) or _text(item.find("date")),
                summary=_clean_text(_text(item.find("description")) or _text(item.find("summary"))),
            )
        )
    return items


def _parse_atom(feed: _Feed, root: ET.Element, limit: int) -> list[RssItemOut]:
    items: list[RssItemOut] = []
    feed_title = _clean_text(_child_text(root, "title") or feed.title)
    entries = [child for child in root if _local_name(child.tag) == "entry"]
    for entry in entries[:limit]:
        url = _safe_item_url(_atom_link(entry))
        if not url:
            continue
        items.append(
            RssItemOut(
                feed_id=feed.id,
                feed_title=feed_title,
                title=_clean_text(_child_text(entry, "title") or "Untitled"),
                url=url,
                published_at=_child_text(entry, "updated") or _child_text(entry, "published"),
                summary=_clean_text(_child_text(entry, "summary") or _child_text(entry, "content")),
            )
        )
    return items


def _atom_link(entry: ET.Element) -> str | None:
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        rel = str(child.attrib.get("rel") or "alternate")
        href = child.attrib.get("href")
        if href and rel == "alternate":
            return href
    return None


def _guid_link(item: ET.Element) -> str | None:
    guid = _text(item.find("guid"))
    return guid if guid and guid.startswith(("https://", "http://")) else None


def _safe_item_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.username or parsed.password or not parsed.netloc:
        return None
    return url.strip()


def _child_text(parent: ET.Element, name: str) -> str | None:
    for child in parent:
        if _local_name(child.tag) == name:
            return _text(child)
    return None


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    unescaped = html.unescape(value)
    without_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", without_tags).strip()[:600]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _short_error(exc: BaseException, *, limit: int = 180) -> str:
    message = " ".join((str(exc).strip() or type(exc).__name__).split())
    return message if len(message) <= limit else message[: limit - 3] + "..."
