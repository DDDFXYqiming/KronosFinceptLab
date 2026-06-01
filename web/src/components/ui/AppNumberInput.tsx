"use client";

import { KeyboardEvent, useEffect, useMemo, useState } from "react";
import { Minus, Plus } from "lucide-react";

export function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function decimalPlaces(value: number): number {
  const text = String(value);
  if (!text.includes(".")) return 0;
  return text.split(".")[1]?.length || 0;
}

function normalizeNumber(value: number, min: number, max: number, step: number, integer: boolean): number {
  const clamped = clampNumber(value, min, max);
  if (integer) return Math.round(clamped);
  const precision = Math.min(6, Math.max(decimalPlaces(step), 0));
  return Number(clamped.toFixed(precision));
}

interface AppNumberInputProps {
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  integer?: boolean;
  ariaLabel: string;
  className?: string;
}

export function AppNumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  integer = true,
  ariaLabel,
  className = "",
}: AppNumberInputProps) {
  const normalizedValue = useMemo(
    () => normalizeNumber(value, min, max, step, integer),
    [value, min, max, step, integer]
  );
  const [draft, setDraft] = useState(String(normalizedValue));

  useEffect(() => {
    setDraft(String(normalizedValue));
    if (normalizedValue !== value) onChange(normalizedValue);
  }, [normalizedValue, onChange, value]);

  const commit = (rawValue: number) => {
    const next = normalizeNumber(rawValue, min, max, step, integer);
    setDraft(String(next));
    onChange(next);
  };

  const handleTextChange = (raw: string) => {
    const allowed = integer ? /^-?\d*$/.test(raw) : /^-?\d*(\.\d*)?$/.test(raw);
    if (!allowed) return;
    setDraft(raw);
    const next = Number(raw);
    if (raw !== "" && raw !== "-" && Number.isFinite(next)) {
      onChange(normalizeNumber(next, min, max, step, integer));
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      commit(normalizedValue + step);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      commit(normalizedValue - step);
    }
  };

  const canDecrement = normalizedValue > min;
  const canIncrement = normalizedValue < max;

  return (
    <div className={`flex min-h-11 min-w-0 overflow-hidden rounded-[10px] border border-slate-700 bg-slate-800 text-white shadow-sm transition-all duration-200 focus-within:ring-4 focus-within:ring-accent/15 ${className}`}>
      <button
        type="button"
        onClick={() => commit(normalizedValue - step)}
        disabled={!canDecrement}
        aria-label={`${ariaLabel} -`}
        className="flex w-11 shrink-0 items-center justify-center border-r border-slate-700 text-slate-300 transition-colors hover:bg-accent/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
      >
        <Minus className="h-4 w-4" />
      </button>
      <input
        value={draft}
        onChange={(event) => handleTextChange(event.target.value)}
        onBlur={() => commit(Number(draft))}
        onKeyDown={handleKeyDown}
        inputMode={integer ? "numeric" : "decimal"}
        aria-label={ariaLabel}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={normalizedValue}
        className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-center text-sm text-white outline-none placeholder:text-muted-foreground"
      />
      <button
        type="button"
        onClick={() => commit(normalizedValue + step)}
        disabled={!canIncrement}
        aria-label={`${ariaLabel} +`}
        className="flex w-11 shrink-0 items-center justify-center border-l border-slate-700 text-slate-300 transition-colors hover:bg-accent/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}
