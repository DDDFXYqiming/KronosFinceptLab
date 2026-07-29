def test_macro_rss_feeds_always_preserve_defaults(monkeypatch):
    monkeypatch.setenv("KRONOS_RSS_VALIDATE_DNS", "0")

    from kronos_fincept.api.routes.ai_analyze import MacroRssFeedIn, _protected_macro_rss_feeds
    from kronos_fincept.api.routes.news import DEFAULT_RSS_FEEDS

    feeds = _protected_macro_rss_feeds([])

    assert [feed["id"] for feed in feeds[:3]] == [feed["id"] for feed in DEFAULT_RSS_FEEDS]

    custom = MacroRssFeedIn(id="custom", title="Custom", url="https://example.com/rss.xml")
    duplicate_default = MacroRssFeedIn(id="fed", title="Renamed Fed", url="https://www.federalreserve.gov/feeds/press_all.xml")

    feeds = _protected_macro_rss_feeds([custom, duplicate_default])
    ids = [feed["id"] for feed in feeds]
    urls = [feed["url"] for feed in feeds]

    assert ids[:3] == ["fed", "sec", "ecb"]
    assert ids.count("fed") == 1
    assert "custom" in ids
    assert "https://example.com/rss.xml" in urls


def test_builtin_rss_urls_remain_usable_when_dns_returns_proxy_addresses(monkeypatch):
    """Built-in public feeds must not fail on proxy DNS synthetic private IPs."""
    import socket

    import pytest

    from kronos_fincept.api.routes.ai_analyze import MacroRssFeedIn
    from kronos_fincept.api.routes.news import DEFAULT_RSS_FEEDS, RssFeedIn

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.93", 443))],
    )

    for feed in DEFAULT_RSS_FEEDS:
        assert MacroRssFeedIn(url=feed["url"]).url == feed["url"]
        assert RssFeedIn(url=feed["url"]).url == feed["url"]

    with pytest.raises(ValueError, match="forbidden address"):
        MacroRssFeedIn(url="https://custom.example/rss.xml")


def test_settings_marks_default_rss_remove_as_disabled():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    settings_page = (root / "web/src/app/settings/page.tsx").read_text(encoding="utf-8")
    rss_lib = (root / "web/src/lib/rssFeeds.ts").read_text(encoding="utf-8")

    assert "disabled={protectedDefault}" in settings_page
    assert "removeRssFeed" in settings_page
    assert "isDefaultRssFeed(normalizeRssFeed(target, 0))" in settings_page
    assert "withProtectedDefaultRssFeeds" in rss_lib
    assert "normalizeRssFeeds([...DEFAULT_RSS_FEEDS, ...feeds])" in rss_lib
