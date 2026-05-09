import { create } from "zustand";
import type { Market } from "@/lib/markets";

export interface WatchlistItem {
  symbol: string;
  market: Market;
  addedAt: string;
  name?: string;
  note?: string;
  tags?: string[];
}

export interface AppPreferences {
  theme: "system" | "dark" | "light";
  defaultMarket: Market;
  defaultRange: "3m" | "1y" | "custom";
  defaultPredLen: number;
}

interface AppState {
  sidebarOpen: boolean;
  watchlist: WatchlistItem[];
  preferences: AppPreferences;
  toggleSidebar: () => void;
  addToWatchlist: (item: WatchlistItem) => void;
  updateWatchlistItem: (symbol: string, market: Market | undefined, patch: Partial<WatchlistItem>) => void;
  replaceWatchlist: (items: WatchlistItem[]) => void;
  removeFromWatchlist: (symbol: string, market?: Market) => void;
  isInWatchlist: (symbol: string, market?: Market) => boolean;
  setPreferences: (patch: Partial<AppPreferences>) => void;
  clearLocalState: () => void;
}

const DEFAULT_PREFERENCES: AppPreferences = {
  theme: "system",
  defaultMarket: "cn",
  defaultRange: "1y",
  defaultPredLen: 5,
};

function normalizeItem(item: WatchlistItem): WatchlistItem {
  return {
    ...item,
    symbol: item.symbol.trim().toUpperCase(),
    market: item.market || "cn",
    addedAt: item.addedAt || new Date().toISOString(),
    tags: Array.isArray(item.tags) ? item.tags.filter(Boolean) : [],
  };
}

function sameItem(a: Pick<WatchlistItem, "symbol" | "market">, b: Pick<WatchlistItem, "symbol" | "market">) {
  return a.symbol === b.symbol && a.market === b.market;
}

function loadWatchlist(): WatchlistItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem("kronos-watchlist");
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.map(normalizeItem) : [];
  } catch {
    return [];
  }
}

function saveWatchlist(items: WatchlistItem[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem("kronos-watchlist", JSON.stringify(items));
}

function loadPreferences(): AppPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = localStorage.getItem("kronos-preferences");
    return raw ? { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) } : DEFAULT_PREFERENCES;
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function savePreferences(preferences: AppPreferences) {
  if (typeof window === "undefined") return;
  localStorage.setItem("kronos-preferences", JSON.stringify(preferences));
}

export const useAppStore = create<AppState>((set, get) => ({
  sidebarOpen: true,
  watchlist: loadWatchlist(),
  preferences: loadPreferences(),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  addToWatchlist: (item) => {
    const normalized = normalizeItem(item);
    const current = get().watchlist;
    if (current.some((w) => sameItem(w, normalized))) return;
    const updated = [...current, normalized];
    saveWatchlist(updated);
    set({ watchlist: updated });
  },

  updateWatchlistItem: (symbol, market, patch) => {
    const normalizedSymbol = symbol.trim().toUpperCase();
    const updated = get().watchlist.map((item) => {
      const isTarget = item.symbol === normalizedSymbol && (!market || item.market === market);
      return isTarget ? normalizeItem({ ...item, ...patch }) : item;
    });
    saveWatchlist(updated);
    set({ watchlist: updated });
  },

  replaceWatchlist: (items) => {
    const seen = new Set<string>();
    const updated = items.map(normalizeItem).filter((item) => {
      const key = `${item.market}:${item.symbol}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return Boolean(item.symbol);
    });
    saveWatchlist(updated);
    set({ watchlist: updated });
  },

  removeFromWatchlist: (symbol, market) => {
    const normalizedSymbol = symbol.trim().toUpperCase();
    const updated = get().watchlist.filter((w) =>
      !(w.symbol === normalizedSymbol && (!market || w.market === market))
    );
    saveWatchlist(updated);
    set({ watchlist: updated });
  },

  isInWatchlist: (symbol, market) => {
    const normalizedSymbol = symbol.trim().toUpperCase();
    return get().watchlist.some((w) => w.symbol === normalizedSymbol && (!market || w.market === market));
  },

  setPreferences: (patch) => {
    const preferences = { ...get().preferences, ...patch };
    savePreferences(preferences);
    set({ preferences });
  },

  clearLocalState: () => {
    if (typeof window !== "undefined") {
      Object.keys(window.sessionStorage)
        .filter((key) => key.startsWith("kronos-"))
        .forEach((key) => window.sessionStorage.removeItem(key));
    }
    savePreferences(DEFAULT_PREFERENCES);
    set({ preferences: DEFAULT_PREFERENCES });
  },
}));
