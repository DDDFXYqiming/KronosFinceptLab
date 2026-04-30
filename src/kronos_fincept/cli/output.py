"""JSON and table output formatters for CLI commands."""

from __future__ import annotations

import json
import sys
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table as RichTable
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def output_json(data: dict[str, Any], file=None) -> None:
    """Output data as formatted JSON."""
    file = file or sys.stdout
    json.dump(data, file, ensure_ascii=False, indent=2)
    file.write("\n")


def output_table(title: str, headers: list[str], rows: list[list[str]], file=None) -> None:
    """Output data as a formatted table using rich (or plain text fallback)."""
    file = file or sys.stdout

    if HAS_RICH:
        try:
            console = Console(file=file, force_terminal=True, no_color=False)
            table = RichTable(
                title=title,
                box=box.ROUNDED,
                show_lines=True,
                title_style="bold cyan",
            )
            for h in headers:
                table.add_column(h, style="white")
            for row in rows:
                table.add_row(*[str(v) for v in row])
            console.print(table)
            return
        except (UnicodeEncodeError, UnicodeError):
            pass  # Fall through to plain text on Windows GBK encoding issues

    # Plain text fallback (also used when rich fails)
    if title:
        file.write(f"\n=== {title} ===\n")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    file.write(header_line + "\n")
    file.write("-+-".join("-" * w for w in widths) + "\n")
    for row in rows:
        line = " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        file.write(line + "\n")


def format_forecast_table(data: dict[str, Any]) -> tuple[str, list[str], list[list[str]]]:
    """Format forecast result as table title/headers/rows."""
    symbol = data.get("symbol", "???")
    pred_len = data.get("pred_len", 0)
    title = f"[Forecast] {symbol} - {pred_len}-Bar"
    headers = ["#", "Timestamp", "Open", "High", "Low", "Close"]
    rows = []
    for i, bar in enumerate(data.get("forecast", []), 1):
        rows.append([
            str(i),
            str(bar.get("timestamp", "")),
            f"{bar.get('open', 0):.2f}",
            f"{bar.get('high', 0):.2f}",
            f"{bar.get('low', 0):.2f}",
            f"{bar.get('close', 0):.2f}",
        ])
    return title, headers, rows


def format_batch_table(data: dict[str, Any]) -> tuple[str, list[str], list[list[str]]]:
    """Format batch result as table."""
    title = "[Batch] Forecast Rankings"
    headers = ["Rank", "Symbol", "Last Close", "Predicted Close", "Return", "Signal"]
    rows = []
    for r in data.get("rankings", []):
        ret = r.get("predicted_return", 0)
        signal = "BUY" if ret > 0.01 else ("SELL" if ret < -0.01 else "HOLD")
        rows.append([
            str(r.get("rank", "")),
            r.get("symbol", ""),
            f"{r.get('last_close', 0):.2f}",
            f"{r.get('predicted_close', 0):.2f}",
            f"{ret:+.4%}",
            signal,
        ])
    return title, headers, rows


def format_data_table(data: dict[str, Any]) -> tuple[str, list[str], list[list[str]]]:
    """Format data result as table."""
    symbol = data.get("symbol", "???")
    count = data.get("count", 0)
    title = f"[Data] {symbol} - {count} rows"
    headers = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]
    rows = []
    for row in data.get("rows", [])[-20:]:  # Show last 20
        rows.append([
            str(row.get("timestamp", ""))[:10],
            f"{row.get('open', 0):.2f}",
            f"{row.get('high', 0):.2f}",
            f"{row.get('low', 0):.2f}",
            f"{row.get('close', 0):.2f}",
            f"{row.get('volume', 0):.0f}",
        ])
    return title, headers, rows


def format_backtest_table(data: dict[str, Any]) -> tuple[str, list[str], list[list[str]]]:
    """Format backtest result as table."""
    title = "[Backtest] Results"
    metrics = data.get("metrics", {})
    headers = ["Metric", "Value"]
    rows = [
        ["Total Return", f"{metrics.get('total_return', 0):.4%}"],
        ["Annualized Return", f"{metrics.get('annualized_return', 0):.4%}"],
        ["Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.4f}"],
        ["Max Drawdown", f"{metrics.get('max_drawdown', 0):.4%}"],
        ["Total Trades", str(metrics.get("total_trades", 0))],
        ["Win Rate", f"{metrics.get('win_rate', 0):.2%}"],
        ["Avg Holding Days", str(metrics.get("avg_holding_days", 0))],
    ]
    return title, headers, rows
