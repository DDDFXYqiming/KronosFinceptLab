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
