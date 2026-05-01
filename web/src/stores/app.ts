import { create } from "zustand";
import { type Market } from "@/lib/defaults";

interface WatchlistItem {
  symbol: string;
  market: Market;
  addedAt: string;
}

interface AppState {
  sidebarOpen: boolean;
  watchlist: WatchlistItem[];
  toggleSidebar: () => void;
  addToWatchlist: (item: WatchlistItem) => void;
  removeFromWatchlist: (symbol: string) => void;
  isInWatchlist: (symbol: string) => boolean;
}

function loadWatchlist(): WatchlistItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem("kronos-watchlist");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveWatchlist(items: WatchlistItem[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem("kronos-watchlist", JSON.stringify(items));
}

export const useAppStore = create<AppState>((set, get) => ({
  sidebarOpen: true,
  watchlist: loadWatchlist(),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  addToWatchlist: (item) => {
    const current = get().watchlist;
    if (current.some((w) => w.symbol === item.symbol)) return;
    const updated = [...current, item];
    saveWatchlist(updated);
    set({ watchlist: updated });
  },

  removeFromWatchlist: (symbol) => {
    const updated = get().watchlist.filter((w) => w.symbol !== symbol);
    saveWatchlist(updated);
    set({ watchlist: updated });
  },

  isInWatchlist: (symbol) => {
    return get().watchlist.some((w) => w.symbol === symbol);
  },
}));
