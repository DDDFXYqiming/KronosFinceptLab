import type { RssFeed } from "@/types/api";

const RSS_FEEDS_STORAGE_KEY = "kronos-rss-feeds";

export const DEFAULT_RSS_FEEDS: RssFeed[] = [
  { id: "fed", title: "Federal Reserve", url: "https://www.federalreserve.gov/feeds/press_all.xml" },
  { id: "sec", title: "SEC", url: "https://www.sec.gov/news/pressreleases.rss" },
  { id: "ecb", title: "ECB", url: "https://www.ecb.europa.eu/rss/press.html" },
];

export const DEFAULT_RSS_FEED_IDS = new Set(DEFAULT_RSS_FEEDS.map((feed) => feed.id).filter(Boolean));
export const DEFAULT_RSS_FEED_URLS = new Set(DEFAULT_RSS_FEEDS.map((feed) => feed.url));

export function normalizeRssFeed(feed: RssFeed, index: number): RssFeed {
  const title = feed.title?.trim();
  const url = feed.url.trim();
  return {
    id: feed.id?.trim() || title || `feed-${index + 1}`,
    title: title || undefined,
    url,
  };
}

export function normalizeRssFeeds(feeds: RssFeed[]): RssFeed[] {
  const seen = new Set<string>();
  return feeds
    .map(normalizeRssFeed)
    .filter((feed) => {
      if (!feed.url || seen.has(feed.url)) return false;
      seen.add(feed.url);
      return true;
    });
}

export function withProtectedDefaultRssFeeds(feeds: RssFeed[]): RssFeed[] {
  return normalizeRssFeeds([...DEFAULT_RSS_FEEDS, ...feeds]);
}

export function isDefaultRssFeed(feed: RssFeed): boolean {
  return Boolean((feed.id && DEFAULT_RSS_FEED_IDS.has(feed.id)) || DEFAULT_RSS_FEED_URLS.has(feed.url));
}

export function getStoredRssFeeds(): RssFeed[] {
  if (typeof window === "undefined") return DEFAULT_RSS_FEEDS;
  try {
    const raw = window.localStorage.getItem(RSS_FEEDS_STORAGE_KEY);
    if (!raw) return DEFAULT_RSS_FEEDS;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? withProtectedDefaultRssFeeds(parsed) : DEFAULT_RSS_FEEDS;
  } catch {
    return DEFAULT_RSS_FEEDS;
  }
}

export function saveStoredRssFeeds(feeds: RssFeed[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(RSS_FEEDS_STORAGE_KEY, JSON.stringify(withProtectedDefaultRssFeeds(feeds)));
}

export function resetStoredRssFeeds(): RssFeed[] {
  saveStoredRssFeeds(DEFAULT_RSS_FEEDS);
  return DEFAULT_RSS_FEEDS;
}
