"use client";

import { KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

export interface AppSelectOption<T extends string> {
  value: T;
  label: string;
  description?: string;
}

interface AppSelectProps<T extends string> {
  value: T;
  options: ReadonlyArray<AppSelectOption<T>>;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
}

export function AppSelect<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className = "",
  disabled = false,
  placeholder,
}: AppSelectProps<T>) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [activeValue, setActiveValue] = useState(value);
  const [placement, setPlacement] = useState<"bottom" | "top">("bottom");

  const selected = useMemo(
    () => options.find((option) => option.value === value),
    [options, value]
  );

  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === activeValue)
  );

  useEffect(() => {
    setActiveValue(value);
  }, [value]);

  useEffect(() => {
    if (!open) return;

    const syncPlacement = () => {
      const rect = rootRef.current?.getBoundingClientRect();
      if (!rect) return;
      const spaceBelow = window.innerHeight - rect.bottom;
      const spaceAbove = rect.top;
      setPlacement(spaceBelow < 280 && spaceAbove > spaceBelow ? "top" : "bottom");
    };

    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    syncPlacement();
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("resize", syncPlacement);
    window.addEventListener("scroll", syncPlacement, true);

    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("resize", syncPlacement);
      window.removeEventListener("scroll", syncPlacement, true);
    };
  }, [open]);

  const commitValue = (nextValue: T) => {
    onChange(nextValue);
    setOpen(false);
  };

  const moveActive = (direction: 1 | -1) => {
    if (options.length === 0) return;
    const nextIndex = (selectedIndex + direction + options.length) % options.length;
    setActiveValue(options[nextIndex].value);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActiveValue(value);
        return;
      }
      moveActive(event.key === "ArrowDown" ? 1 : -1);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) {
        commitValue(activeValue);
      } else {
        setOpen(true);
        setActiveValue(value);
      }
      return;
    }

    if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className={`relative min-w-0 ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-controls={listboxId}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => {
          setOpen((current) => !current);
          setActiveValue(value);
        }}
        onKeyDown={handleKeyDown}
        className="app-input flex items-center justify-between gap-3 text-left text-sm shadow-sm transition-all duration-200 hover:border-accent/40 focus:ring-4 focus:ring-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="min-w-0 truncate">
          {selected?.label || placeholder || ariaLabel}
        </span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
        >
          <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
          className={`absolute left-0 z-50 w-full min-w-[12rem] overflow-hidden rounded-xl border border-[#374151] bg-[#111827] p-1 shadow-2xl shadow-black/35 ring-1 ring-white/10 backdrop-blur ${placement === "top" ? "bottom-[calc(100%+0.5rem)]" : "top-[calc(100%+0.5rem)]"}`}
        >
          <div className="max-h-64 overflow-y-auto overscroll-contain">
            {options.map((option) => {
              const selectedOption = option.value === value;
              const activeOption = option.value === activeValue;
              return (
                <button
                  type="button"
                  key={option.value}
                  role="option"
                  aria-selected={selectedOption}
                  onMouseEnter={() => setActiveValue(option.value)}
                  onClick={() => commitValue(option.value)}
                  className={`flex w-full min-w-0 items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors duration-150 ${
                    activeOption
                      ? "bg-accent/20 text-white"
                      : "text-slate-300 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`h-2 w-2 shrink-0 rounded-full ${selectedOption ? "bg-accent" : "bg-transparent"}`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{option.label}</span>
                    {option.description && (
                      <span className="mt-0.5 block truncate text-xs text-slate-400">
                        {option.description}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
