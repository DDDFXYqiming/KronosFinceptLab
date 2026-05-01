"""HTML report generator for strategy backtests.

Generates self-contained HTML reports with embedded matplotlib charts (base64 PNG),
supporting single-strategy reports, multi-strategy comparison, and benchmark overlay.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Matplotlib setup (must happen before any pyplot import) ──────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Dark theme palette matching the web frontend
BG_COLOR = "#0A0E1A"
TEXT_COLOR = "#E0E0E0"
ACCENT_COLOR = "#4FC3F7"
GREEN_COLOR = "#4CAF50"
RED_COLOR = "#EF5350"
CARD_BG = "#131827"
CHART_GRID = "#1E2A3A"

plt.rcParams.update({
    "figure.facecolor": BG_COLOR,
    "axes.facecolor": BG_COLOR,
    "axes.edgecolor": CHART_GRID,
    "axes.labelcolor": TEXT_COLOR,
    "axes.titlecolor": TEXT_COLOR,
    "xtick.color": TEXT_COLOR,
    "ytick.color": TEXT_COLOR,
    "grid.color": CHART_GRID,
    "legend.facecolor": CARD_BG,
    "legend.edgecolor": CHART_GRID,
    "legend.labelcolor": TEXT_COLOR,
})

DISCLAIMER = (
    "IMPORTANT DISCLAIMER: Backtest results are for research purposes only. "
    "Past performance does not guarantee future results. This is not financial advice."
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _fig_to_base64(fig: matplotlib.figure.Figure) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor=BG_COLOR, edgecolor="none")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _pct(v: float) -> str:
    """Format a float as a percentage string."""
    return f"{v * 100:.2f}%"


def _fmt(v: float, dec: int = 4) -> str:
    """Format a float with given decimal places."""
    return f"{v:.{dec}f}"


# ── Chart generators ────────────────────────────────────────────────────

def _equity_curve_chart(
    equity_curve: list[dict[str, Any]],
    benchmark_curve: list[dict[str, Any]] | None = None,
    strategy_name: str = "Strategy",
    benchmark_name: str = "Benchmark",
) -> str:
    """Generate equity curve chart as base64 PNG."""
    dates = [e["date"][:10] for e in equity_curve]
    equities = [e["equity"] for e in equity_curve]

    fig, ax = plt.subplots(figsize=(10, 4.5))

    # Normalize to percentage returns starting at 100
    base = equities[0]
    pct_ret = [(e / base - 1) * 100 for e in equities]
    ax.plot(dates, pct_ret, color=ACCENT_COLOR, linewidth=1.8,
            label=strategy_name)

    # Benchmark overlay
    if benchmark_curve:
        bench_dates = [b["date"][:10] for b in benchmark_curve]
        bench_prices = [b["close"] for b in benchmark_curve]
        bench_base = bench_prices[0]
        bench_pct = [(p / bench_base - 1) * 100 for p in bench_prices]
        ax.plot(bench_dates, bench_pct, color=GREEN_COLOR, linewidth=1.2,
                alpha=0.7, label=benchmark_name)

    ax.set_ylabel("Return (%)", color=TEXT_COLOR)
    ax.set_title(f"Equity Curve — {strategy_name}", color=TEXT_COLOR)
    ax.legend()
    ax.grid(True, alpha=0.2)

    # Show fewer x-labels
    step = max(1, len(dates) // 8)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                       rotation=30, ha="right", fontsize=8)

    fig.tight_layout()
    b64 = _fig_to_base64(fig)
    plt.close(fig)
    return b64


def _drawdown_chart(equity_curve: list[dict[str, Any]]) -> str:
    """Generate drawdown chart as base64 PNG."""
    equities = [e["equity"] for e in equity_curve]
    dates = [e["date"][:10] for e in equity_curve]

    peak = equities[0]
    drawdowns = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
        drawdowns.append(-dd)

    fig, ax = plt.subplots(figsize=(10, 2.5))
    ax.fill_between(range(len(drawdowns)), 0, drawdowns,
                     color=RED_COLOR, alpha=0.4, step="mid")
    ax.plot(drawdowns, color=RED_COLOR, linewidth=1.0)
    ax.set_ylabel("Drawdown (%)", color=TEXT_COLOR)
    ax.set_title("Drawdown", color=TEXT_COLOR)
    ax.grid(True, alpha=0.2)

    step = max(1, len(dates) // 8)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                       rotation=30, ha="right", fontsize=8)

    fig.tight_layout()
    b64 = _fig_to_base64(fig)
    plt.close(fig)
    return b64


# ── HTML template ───────────────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Backtest Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    background: {bg};
    color: {text};
    padding: 24px;
    line-height: 1.5;
}}
.report {{
    max-width: 960px;
    margin: 0 auto;
}}
h1 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 4px; }}
h2 {{ font-size: 1.15rem; font-weight: 500; margin: 24px 0 12px;
      border-bottom: 1px solid {grid}; padding-bottom: 6px; }}
.subtitle {{ color: #8892A4; font-size: 0.85rem; margin-bottom: 20px; }}
.card {{
    background: {card};
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
}}
.metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px;
}}
.metric {{
    text-align: center;
    padding: 8px;
}}
.metric-value {{
    font-size: 1.3rem;
    font-weight: 600;
    color: {accent};
}}
.metric-label {{
    font-size: 0.75rem;
    color: #8892A4;
    margin-top: 2px;
}}
.chart-img {{
    width: 100%;
    height: auto;
    border-radius: 6px;
}}
.disclaimer {{
    margin-top: 24px;
    padding: 12px 16px;
    border-radius: 8px;
    background: {card};
    border-left: 3px solid {accent};
    font-size: 0.8rem;
    color: #8892A4;
    line-height: 1.4;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}}
th, td {{
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid {grid};
}}
th {{
    color: #8892A4;
    font-weight: 500;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.footer {{
    text-align: center;
    margin-top: 20px;
    font-size: 0.75rem;
    color: #5A6577;
}}
@media print {{
    body {{ background: #fff; color: #111; }}
    .card {{ background: #f5f5f5; }}
    .disclaimer {{ background: #f5f5f5; }}
    .subtitle, .metric-label, th {{ color: #666; }}
    .metric-value {{ color: #1565C0; }}
    .footer {{ color: #999; }}
}}
</style>
</head>
<body>
<div class="report">
<h1>{title}</h1>
<div class="subtitle">{strategy_name} &middot; {date_range}</div>

<div class="card">
  <div class="metrics-grid">
    {metrics_html}
  </div>
</div>

<h2>Equity Curve</h2>
<div class="card">
  <img class="chart-img" src="data:image/png;base64,{equity_chart}" alt="Equity Curve">
</div>

<h2>Drawdown</h2>
<div class="card">
  <img class="chart-img" src="data:image/png;base64,{drawdown_chart}" alt="Drawdown">
</div>

{trades_section}

<div class="disclaimer">{disclaimer}</div>
<div class="footer">Generated by KronosFinceptLab &middot; {generated_at}</div>
</div>
</body>
</html>"""


# ── BacktestReportGenerator ─────────────────────────────────────────────

class BacktestReportGenerator:
    """Generates self-contained HTML reports from backtest results."""

    def generate_html(
        self,
        symbol: str,
        metrics: dict[str, Any],
        equity_curve: list[dict[str, Any]],
        trades: list[dict[str, Any]] | None = None,
        benchmark_data: list[dict[str, Any]] | None = None,
        strategy_name: str = "Ranking Strategy",
    ) -> str:
        """Generate a complete HTML report with embedded charts.

        Args:
            symbol: Ticker symbol(s) displayed in the report.
            metrics: Dict with keys: total_return, annualized_return,
                sharpe_ratio, max_drawdown, total_trades, win_rate.
            equity_curve: List of {date, equity, return, selected}.
            trades: Optional list of trade dicts {symbol, entry, exit, return}.
            benchmark_data: Optional list of {date, close} for benchmark
                overlay on the equity curve.
            strategy_name: Display name for the strategy.

        Returns:
            Self-contained HTML string.
        """
        if not equity_curve:
            raise ValueError("equity_curve must not be empty")

        # Build date range
        start_date = equity_curve[0]["date"][:10]
        end_date = equity_curve[-1]["date"][:10]
        date_range = f"{start_date} to {end_date}"

        # Metrics cards
        m = metrics
        metric_items = [
            ("Total Return", _pct(m.get("total_return", 0))),
            ("Annualized Return", _pct(m.get("annualized_return", 0))),
            ("Sharpe Ratio", _fmt(m.get("sharpe_ratio", 0), 2)),
            ("Max Drawdown", _pct(m.get("max_drawdown", 0))),
            ("Win Rate", _pct(m.get("win_rate", 0))),
            ("Total Trades", str(m.get("total_trades", 0))),
        ]
        metrics_html = "".join(
            f'<div class="metric"><div class="metric-value">{v}</div>'
            f'<div class="metric-label">{k}</div></div>'
            for k, v in metric_items
        )

        # Charts
        equity_chart = self.equity_curve_chart(equity_curve, benchmark_data)
        drawdown_chart = self.drawdown_chart(equity_curve)

        # Trades section
        trades_section = ""
        if trades:
            trade_rows = "".join(
                f"<tr><td>{t.get('symbol', '')}</td>"
                f"<td>{t.get('entry', '')}</td>"
                f"<td>{t.get('exit', '')}</td>"
                f"<td>{_pct(t.get('return', 0))}</td></tr>"
                for t in trades
            )
            trades_section = (
                f"<h2>Trades</h2>\n<div class=\"card\">\n"
                f"<table><thead><tr>"
                f"<th>Symbol</th><th>Entry</th><th>Exit</th><th>Return</th>"
                f"</tr></thead><tbody>{trade_rows}</tbody></table>\n</div>"
            )

        # Timestamp
        from datetime import datetime, timezone
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        html = _HTML_TEMPLATE.format(
            title=f"Backtest Report — {symbol}",
            strategy_name=strategy_name,
            date_range=date_range,
            metrics_html=metrics_html,
            equity_chart=equity_chart,
            drawdown_chart=drawdown_chart,
            trades_section=trades_section,
            disclaimer=DISCLAIMER,
            generated_at=generated_at,
            bg=BG_COLOR,
            text=TEXT_COLOR,
            card=CARD_BG,
            grid=CHART_GRID,
            accent=ACCENT_COLOR,
        )
        return html

    # ── Chart methods (public for reuse) ──────────────────────────────

    def equity_curve_chart(
        self,
        equity_curve: list[dict[str, Any]],
        benchmark_curve: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate equity curve chart, return base64 PNG string."""
        return _equity_curve_chart(equity_curve, benchmark_curve)

    def drawdown_chart(
        self,
        equity_curve: list[dict[str, Any]],
    ) -> str:
        """Generate drawdown chart as base64 PNG."""
        return _drawdown_chart(equity_curve)

    # ── Export ────────────────────────────────────────────────────────

    def export_html(self, html: str, output_path: str) -> str:
        """Write HTML to file, return path."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Backtest report written to %s", output_path)
        return output_path


# ── Multi-strategy comparison ────────────────────────────────────────────

def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def compare_strategies(results: list[dict[str, Any]]) -> str:
    """Compare multiple strategy backtest results in an HTML report.

    Each result dict::

        {
            "name": str,
            "metrics": {"total_return": ..., "sharpe_ratio": ..., ...},
            "equity_curve": [{"date": ..., "equity": ...}, ...],
        }

    Returns:
        Self-contained HTML string.
    """
    if not results:
        raise ValueError("results list must not be empty")

    # ── Overlaid equity curve ──
    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = [ACCENT_COLOR, GREEN_COLOR, "#FFB74D", "#CE93D8", "#81D4FA"]
    date_range_str = ""

    for idx, res in enumerate(results):
        curve = res.get("equity_curve", [])
        name = res.get("name", f"Strategy {idx + 1}")
        if not curve:
            continue
        if not date_range_str:
            sd = curve[0]["date"][:10]
            ed = curve[-1]["date"][:10]
            date_range_str = f"{sd} to {ed}"
        dates = [e["date"][:10] for e in curve]
        equities = [e["equity"] for e in curve]
        base = equities[0]
        pct_ret = [(e / base - 1) * 100 for e in equities]
        color = colors[idx % len(colors)]
        ax.plot(dates, pct_ret, color=color, linewidth=1.5, label=name, alpha=0.85)

    ax.set_ylabel("Return (%)", color=TEXT_COLOR)
    ax.set_title("Strategy Comparison — Equity Curves", color=TEXT_COLOR)
    ax.legend()
    ax.grid(True, alpha=0.2)
    if date_range_str and results:
        curve0 = results[0].get("equity_curve", [])
        if curve0:
            step = max(1, len(curve0) // 8)
            dates0 = [e["date"][:10] for e in curve0]
            ax.set_xticks(range(0, len(dates0), step))
            ax.set_xticklabels(
                [dates0[i] for i in range(0, len(dates0), step)],
                rotation=30, ha="right", fontsize=8,
            )
    fig.tight_layout()
    compare_chart = _fig_to_base64(fig)
    plt.close(fig)

    # ── Metrics table rows ──
    metric_keys = [
        ("Total Return", "total_return", _pct),
        ("Annualized Return", "annualized_return", _pct),
        ("Sharpe Ratio", "sharpe_ratio", lambda v: _fmt(v, 2)),
        ("Max Drawdown", "max_drawdown", _pct),
        ("Win Rate", "win_rate", _pct),
        ("Total Trades", "total_trades", str),
    ]

    thead = "<thead><tr><th>Metric</th>"
    for res in results:
        thead += f"<th>{_escape_html(res.get('name', '?'))}</th>"
    thead += "</tr></thead>"

    tbody = "<tbody>"
    for label, key, fmt_fn in metric_keys:
        tbody += f"<tr><td>{label}</td>"
        for res in results:
            val = res.get("metrics", {}).get(key, "—")
            if isinstance(val, (int, float)):
                val = fmt_fn(val)
            tbody += f"<td>{val}</td>"
        tbody += "</tr>"
    tbody += "</tbody>"

    from datetime import datetime, timezone
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Strategy Comparison — Backtest Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    background: {BG_COLOR};
    color: {TEXT_COLOR};
    padding: 24px;
    line-height: 1.5;
}}
.report {{ max-width: 960px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 4px; }}
h2 {{ font-size: 1.15rem; font-weight: 500; margin: 24px 0 12px;
      border-bottom: 1px solid {CHART_GRID}; padding-bottom: 6px; }}
.subtitle {{ color: #8892A4; font-size: 0.85rem; margin-bottom: 20px; }}
.card {{
    background: {CARD_BG};
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
    overflow-x: auto;
}}
.chart-img {{ width: 100%; height: auto; border-radius: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
th, td {{ padding: 8px 12px; text-align: left;
          border-bottom: 1px solid {CHART_GRID}; }}
th {{ color: #8892A4; font-weight: 500; font-size: 0.75rem;
      text-transform: uppercase; letter-spacing: 0.5px; }}
.disclaimer {{
    margin-top: 24px; padding: 12px 16px; border-radius: 8px;
    background: {CARD_BG}; border-left: 3px solid {ACCENT_COLOR};
    font-size: 0.8rem; color: #8892A4;
}}
.footer {{ text-align: center; margin-top: 20px;
          font-size: 0.75rem; color: #5A6577; }}
@media print {{
    body {{ background: #fff; color: #111; }}
    .card {{ background: #f5f5f5; }}
    .disclaimer {{ background: #f5f5f5; }}
    .subtitle, th {{ color: #666; }}
    .footer {{ color: #999; }}
}}
</style>
</head>
<body>
<div class="report">
<h1>Strategy Comparison</h1>
<div class="subtitle">{date_range_str}</div>

<h2>Equity Curves</h2>
<div class="card">
  <img class="chart-img" src="data:image/png;base64,{compare_chart}" alt="Strategy Comparison">
</div>

<h2>Performance Metrics</h2>
<div class="card">
  <table>{thead}{tbody}</table>
</div>

<div class="disclaimer">{DISCLAIMER}</div>
<div class="footer">Generated by KronosFinceptLab &middot; {generated_at}</div>
</div>
</body>
</html>"""
    return html
