"use client";

import { useMemo, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { useSessionState } from "@/lib/useSessionState";
import type { RssFeed, RssItem } from "@/types/api";

const DEFAULT_FEEDS: RssFeed[] = [
  { id: "fed", title: "Federal Reserve", url: "https://www.federalreserve.gov/feeds/press_all.xml" },
  { id: "sec", title: "SEC", url: "https://www.sec.gov/news/pressreleases.rss" },
  { id: "ecb", title: "ECB", url: "https://www.ecb.europa.eu/rss/press.html" },
];

function normalizeFeed(feed: RssFeed, index: number): RssFeed {
  const title = feed.title?.trim();
  const url = feed.url.trim();
  return {
    id: feed.id?.trim() || title || `feed-${index + 1}`,
    title: title || undefined,
    url,
  };
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

export default function NewsPage() {
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
    setFeeds((current) => current.filter((feed, index) => normalizeFeed(feed, index).id !== feedId));
  };

  const resetFeeds = () => {
    setFeeds(DEFAULT_FEEDS);
    setItems([]);
    setErrors({});
    setError("");
  };

  const refreshNews = async () => {
    if (activeFeeds.length === 0) {
      setError("请先添加至少一个 RSS 源。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await api.fetchRss({ feeds: activeFeeds, limit_per_feed: limit });
      setItems(response.items);
      setErrors(response.errors || {});
    } catch (exc) {
      setError(formatApiError(exc, "RSS 获取失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>新闻</SectionLabel>
      <h1 className="page-title">新闻 / RSS</h1>

      <Card>
        <CardTitle subtitle="RSS 地址必须使用 HTTPS，后端会拦截本机和内网地址。">订阅源</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_2fr_10rem]">
          <div>
            <label className="field-label">名称</label>
            <input value={title} onChange={(event) => setTitle(event.target.value)} className="app-input mt-1" placeholder="例如 Fed" />
          </div>
          <div>
            <label className="field-label">RSS URL</label>
            <input value={url} onChange={(event) => setUrl(event.target.value)} className="app-input mt-1 font-mono" placeholder="https://..." />
          </div>
          <div>
            <label className="field-label">每源条数</label>
            <input type="number" min={1} max={20} value={limit} onChange={(event) => setLimit(Math.min(20, Math.max(1, Number(event.target.value))))} className="app-input mt-1" />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:flex-wrap">
          <Button onClick={addFeed}>添加源</Button>
          <Button variant="secondary" onClick={refreshNews} loading={loading}>刷新新闻</Button>
          <Button variant="secondary" onClick={resetFeeds}>恢复默认源</Button>
        </div>
      </Card>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}

      <Card>
        <CardTitle>已启用源 ({activeFeeds.length})</CardTitle>
        <div className="space-y-2">
          {activeFeeds.map((feed) => (
            <div key={feed.id || feed.url} className="flex flex-col gap-2 rounded-lg border border-border p-3 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <p className="font-medium">{feed.title || feed.id}</p>
                <p className="truncate font-mono text-xs text-muted-foreground">{feed.url}</p>
                {errors[feed.id || feed.url] && <p className="mt-1 text-xs text-error">{errors[feed.id || feed.url]}</p>}
              </div>
              <Button variant="ghost" onClick={() => removeFeed(feed.id || feed.url)}>移除</Button>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardTitle>最新条目 ({items.length})</CardTitle>
        {items.length === 0 ? (
          <div className="py-10 text-center text-muted-foreground">暂无新闻条目</div>
        ) : (
          <div className="table-scroll">
            <table className="min-w-[52rem] w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">来源</th>
                  <th className="py-2 text-left">标题</th>
                  <th className="py-2 text-left">时间</th>
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
                    <td className="py-3 align-top font-mono text-xs text-muted-foreground">{formatDate(item.published_at)}</td>
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
