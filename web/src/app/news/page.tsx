"use client";

import { useMemo, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { Language } from "@/lib/i18n";
import type { RssFeed, RssItem } from "@/types/api";

const DEFAULT_FEEDS: RssFeed[] = [
  { id: "fed", title: "Federal Reserve", url: "https://www.federalreserve.gov/feeds/press_all.xml" },
  { id: "sec", title: "SEC", url: "https://www.sec.gov/news/pressreleases.rss" },
  { id: "ecb", title: "ECB", url: "https://www.ecb.europa.eu/rss/press.html" },
];

const DEFAULT_FEED_IDS = new Set(DEFAULT_FEEDS.map((feed) => feed.id).filter(Boolean));
const DEFAULT_FEED_URLS = new Set(DEFAULT_FEEDS.map((feed) => feed.url));

function normalizeFeed(feed: RssFeed, index: number): RssFeed {
  const title = feed.title?.trim();
  const url = feed.url.trim();
  return {
    id: feed.id?.trim() || title || `feed-${index + 1}`,
    title: title || undefined,
    url,
  };
}

function isDefaultFeed(feed: RssFeed): boolean {
  return Boolean((feed.id && DEFAULT_FEED_IDS.has(feed.id)) || DEFAULT_FEED_URLS.has(feed.url));
}

function tx(language: Language, zh: string, en: string): string {
  return language === "en-US" ? en : zh;
}

function formatDate(value: string | null | undefined, language: Language): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(language, { hour12: false });
}

export default function NewsPage() {
  const language = useAppStore((state) => state.preferences.language);
  const [feeds, setFeeds] = useSessionState<RssFeed[]>("kronos-news-feeds", DEFAULT_FEEDS);
  const [title, setTitle] = useSessionState("kronos-news-title", "");
  const [url, setUrl] = useSessionState("kronos-news-url", "");
  const [limit, setLimit] = useSessionState("kronos-news-limit", 8);
  const [items, setItems] = useSessionState<RssItem[]>("kronos-news-items", []);
  const [errors, setErrors] = useSessionState<Record<string, string>>("kronos-news-errors", {});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const activeFeeds = useMemo(() => feeds.map(normalizeFeed).filter((feed) => feed.url), [feeds]);

  const addFeed = () => {
    const feed = normalizeFeed({ title, url }, feeds.length);
    if (!feed.url) return;
    setFeeds((current) => [...current, feed]);
    setTitle("");
    setUrl("");
  };

  const removeFeed = (feedId: string) => {
    setFeeds((current) => current.filter((feed, index) => {
      const normalized = normalizeFeed(feed, index);
      return isDefaultFeed(normalized) || normalized.id !== feedId;
    }));
  };

  const resetFeeds = () => {
    setFeeds(DEFAULT_FEEDS);
    setItems([]);
    setErrors({});
    setError("");
  };

  const refreshNews = async () => {
    if (activeFeeds.length === 0) {
      setError(tx(language, "请先添加至少一个 RSS 源。", "Add at least one RSS feed first."));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await api.fetchRss({ feeds: activeFeeds, limit_per_feed: limit });
      setItems(response.items);
      setErrors(response.errors || {});
    } catch (exc) {
      setError(formatApiError(exc, tx(language, "RSS 获取失败", "Failed to fetch RSS items")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>{tx(language, "新闻", "News")}</SectionLabel>
      <h1 className="page-title">{tx(language, "新闻 / RSS", "News / RSS")}</h1>

      <Card>
        <CardTitle subtitle={tx(language, "RSS 地址必须使用 HTTPS，后端会拦截本机和内网地址。", "RSS URLs must use HTTPS; the backend blocks localhost and private-network addresses.")}>{tx(language, "订阅源", "Feeds")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_2fr_10rem]">
          <div>
            <label className="field-label">{tx(language, "名称", "Name")}</label>
            <input value={title} onChange={(event) => setTitle(event.target.value)} className="app-input mt-1" placeholder={tx(language, "例如 Fed", "e.g. Fed")} />
          </div>
          <div>
            <label className="field-label">RSS URL</label>
            <input value={url} onChange={(event) => setUrl(event.target.value)} className="app-input mt-1 font-mono" placeholder="https://..." />
          </div>
          <div>
            <label className="field-label">{tx(language, "每源条数", "Items per feed")}</label>
            <input type="number" min={1} max={20} value={limit} onChange={(event) => setLimit(Math.min(20, Math.max(1, Number(event.target.value))))} className="app-input mt-1" />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:flex-wrap">
          <Button onClick={addFeed}>{tx(language, "添加源", "Add feed")}</Button>
          <Button variant="secondary" onClick={refreshNews} loading={loading}>{tx(language, "刷新新闻", "Refresh news")}</Button>
          <Button variant="secondary" onClick={resetFeeds}>{tx(language, "恢复默认源", "Restore defaults")}</Button>
        </div>
      </Card>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}

      <Card>
        <CardTitle>{tx(language, "已启用源", "Enabled Feeds")} ({activeFeeds.length})</CardTitle>
        <div className="space-y-2">
          {activeFeeds.map((feed) => {
            const defaultFeed = isDefaultFeed(feed);
            return (
              <div key={feed.id || feed.url} className="flex flex-col gap-2 rounded-lg border border-border p-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <p className="font-medium">{feed.title || feed.id}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground">{feed.url}</p>
                  {errors[feed.id || feed.url] && <p className="mt-1 text-xs text-error">{errors[feed.id || feed.url]}</p>}
                </div>
                <Button variant="ghost" disabled={defaultFeed} onClick={() => removeFeed(feed.id || feed.url)}>{tx(language, "移除", "Remove")}</Button>
              </div>
            );
          })}
        </div>
      </Card>

      <Card>
        <CardTitle>{tx(language, "最新条目", "Latest Items")} ({items.length})</CardTitle>
        {items.length === 0 ? (
          <div className="py-10 text-center text-muted-foreground">{tx(language, "暂无新闻条目", "No news items yet")}</div>
        ) : (
          <div className="table-scroll">
            <table className="min-w-[52rem] w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">{tx(language, "来源", "Source")}</th>
                  <th className="py-2 text-left">{tx(language, "标题", "Title")}</th>
                  <th className="py-2 text-left">{tx(language, "时间", "Time")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={`${item.feed_id}-${item.url}`} className="border-b border-gray-800 hover:bg-surface-overlay/50">
                    <td className="py-3 align-top text-muted-foreground">{item.feed_title || item.feed_id}</td>
                    <td className="py-3 align-top">
                      <a href={item.url} target="_blank" rel="noreferrer" className="font-medium text-primary-light hover:underline">{item.title}</a>
                      {item.summary && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.summary}</p>}
                    </td>
                    <td className="py-3 align-top font-mono text-xs text-muted-foreground">{formatDate(item.published_at, language)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
