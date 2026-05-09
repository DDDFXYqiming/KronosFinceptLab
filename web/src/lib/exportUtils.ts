import type { ForecastRow } from "@/types/api";

export type CsvCell = string | number | boolean | null | undefined;

export function validateDateRange(startDate: string, endDate: string): string | null {
  const pattern = /^\d{8}$/;
  if (!pattern.test(startDate) || !pattern.test(endDate)) {
    return "日期格式必须为 YYYYMMDD。";
  }
  if (startDate > endDate) {
    return "开始日期不得晚于结束日期。";
  }
  return null;
}

export function escapeCsvCell(value: CsvCell): string {
  const text = value === null || value === undefined ? "" : String(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function toCsv(headers: string[], rows: CsvCell[][]): string {
  return [headers, ...rows]
    .map((row) => row.map(escapeCsvCell).join(","))
    .join("\n");
}

export function makeDatedFilename(scope: string, symbols: string | string[], startDate?: string, endDate?: string, ext = "csv") {
  const symbolText = Array.isArray(symbols) ? symbols.join("_") : symbols;
  const safeSymbols = symbolText.replace(/[^a-zA-Z0-9_+-]+/g, "_").slice(0, 80) || "all";
  const range = startDate && endDate ? `_${startDate}_${endDate}` : "";
  return `${scope}_${safeSymbols}${range}.${ext}`;
}

export function downloadTextFile(filename: string, content: string, mime = "text/csv;charset=utf-8") {
  if (typeof window === "undefined") return;
  const blob = new Blob([content], { type: mime });
  const url = window.URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = filename;
  window.document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function ohlcvRowsToCsv(rows: ForecastRow[]): string {
  return toCsv(
    ["timestamp", "open", "high", "low", "close", "volume", "amount"],
    rows.map((row) => [
      row.timestamp,
      row.open,
      row.high,
      row.low,
      row.close,
      row.volume ?? "",
      row.amount ?? "",
    ])
  );
}
