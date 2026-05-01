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
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined" || options.preferInitial) {
      return initialValue;
    }

    try {
      const raw = window.sessionStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Ignore storage quota or private-mode errors; in-memory React state still works.
    }
  }, [key, value]);

  return [value, setValue];
}
