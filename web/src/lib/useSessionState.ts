"use client";

import { Dispatch, SetStateAction, useEffect, useState } from "react";

interface SessionStateOptions {
  preferInitial?: boolean;
}

export function useSessionState<T>(
  key: string,
  initialValue: T,
  options: SessionStateOptions = {}
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(initialValue);
  const [hasHydrated, setHasHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (options.preferInitial) {
      setHasHydrated(true);
      return;
    }
    try {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        setValue(JSON.parse(raw) as T);
      }
    } catch {
      // Ignore malformed persisted state; the initial value remains valid.
    } finally {
      setHasHydrated(true);
    }
  }, [key, options.preferInitial]);

  useEffect(() => {
    if (typeof window === "undefined" || !hasHydrated) return;

    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Ignore storage quota or private-mode errors; in-memory React state still works.
    }
  }, [hasHydrated, key, value]);

  return [value, setValue];
}
