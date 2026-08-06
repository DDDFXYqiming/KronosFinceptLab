"""Dividend ETF rotation provider (红利ETF 轮动).

Fixed candidate pool of A-share red-dividend ETFs. For each ETF we combine:
- 60-trading-day price momentum (AkShare Sina daily history);
- annual dividend yield approximated from the latest two annual cumulative
  distributions divided by the current price (AkShare Sina dividend records).

Rotation rank = average of the dividend-yield rank and the momentum rank.
When every candidate has negative momentum the provider emits a
"cash / wait for pullback" hint. All outputs are facts for the LLM.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

logger = logging.getLogger(__name__)


RELEVANCE_PATTERN = re.compile(
    r"红利|股息|分红|高股息|红利ETF|ETF轮动|轮动|红利低波|红利指数",
    re.IGNORECASE,
)

# Fixed candidate pool: (sina code, display label)
ETF_UNIVERSE = (
    ("sh510880", "红利ETF(510880, 上证红利)"),
    ("sh515080", "中证红利ETF(515080)"),
    ("sh512890", "红利低波ETF(512890)"),
)

_CACHE: dict[str, tuple[float, list[MacroSignal]]] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 30 * 60


def _relevant(query: MacroQuery) -> bool:
    text = " ".join(
        part for part in (query.question or "", " ".join(query.symbols or ()), query.market or "") if part
    )
    return bool(RELEVANCE_PATTERN.search(text))


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _etf_metrics(sina_code: str) -> dict[str, Any] | None:
    """Return {price, momentum_60d, yield_pct, annual_dividend} or None."""
    try:
        import akshare as ak

        hist = ak.fund_etf_hist_sina(symbol=sina_code)
        if hist is None or getattr(hist, "empty", True):
            return None
        closes = [_number(value) for value in hist["close"].tolist()]
        closes = [value for value in closes if value is not None]
        if len(closes) < 61:
            return None
        price = closes[-1]
        momentum = (price / closes[-61] - 1.0) * 100.0

        annual_dividend: float | None = None
        try:
            dividends = ak.fund_etf_dividend_sina(symbol=sina_code)
            if dividends is not None and not dividends.empty and len(dividends) >= 2:
                cumulative = [_number(value) for value in dividends["累计分红"].tolist()]
                cumulative = [value for value in cumulative if value is not None]
                if len(cumulative) >= 2:
                    annual_dividend = max(0.0, cumulative[-1] - cumulative[-2])
        except Exception as exc:
            logger.debug("[dividend_etf_rotation] dividend history failed %s: %s", sina_code, exc)

        yield_pct = annual_dividend / price * 100.0 if annual_dividend is not None and price > 0 else None
        return {
            "price": round(price, 4),
            "momentum_60d": round(momentum, 3),
            "annual_dividend": round(annual_dividend, 4) if annual_dividend is not None else None,
            "yield_pct": round(yield_pct, 3) if yield_pct is not None else None,
        }
    except Exception as exc:
        logger.debug("[dividend_etf_rotation] %s failed: %s", sina_code, exc)
        return None


class DividendEtfRotationProvider(MacroProvider):
    provider_id = "dividend_etf_rotation"
    display_name = "红利ETF轮动"
    capabilities = ("dividend", "etf", "rotation")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _relevant(query):
            return []
        cache_key = query.cache_key()
        with _LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _TTL_SECONDS:
                return cached[1]

        metrics: dict[str, dict[str, Any]] = {}
        for sina_code, label in ETF_UNIVERSE:
            item = _etf_metrics(sina_code)
            if item:
                item["label"] = label
                metrics[sina_code] = item
        signals: list[MacroSignal] = []
        if not metrics:
            with _LOCK:
                _CACHE[cache_key] = (time.monotonic(), signals)
            return signals

        with_yield = {code: item for code, item in metrics.items() if item.get("yield_pct") is not None}
        if with_yield:
            yield_rank = {
                code: index
                for index, code in enumerate(sorted(with_yield, key=lambda c: with_yield[c]["yield_pct"], reverse=True))
            }
            momentum_rank = {
                code: index
                for index, code in enumerate(sorted(with_yield, key=lambda c: with_yield[c]["momentum_60d"], reverse=True))
            }
            scores = {code: (yield_rank[code] + momentum_rank[code]) / 2.0 for code in with_yield}
            ranked = sorted(with_yield, key=lambda c: scores[c])
            top = ranked[0]
            all_negative = all(item["momentum_60d"] < 0 for item in metrics.values())
            top_label = metrics[top]["label"]
            signals.append(
                MacroSignal(
                    source=self.provider_id,
                    signal_type="dividend_etf_rotation",
                    value=top_label,
                    interpretation=(
                        f"红利ETF轮动排序：{' > '.join(metrics[c]['label'] for c in ranked)}；"
                        f"当前首选{top_label}（股息率{metrics[top]['yield_pct']:.2f}%，60日动量{metrics[top]['momentum_60d']:+.1f}%）。"
                        + ("全部候选60日动量为负，优先现金/等回调。" if all_negative else "")
                    ),
                    time_horizon="monthly",
                    confidence=0.7,
                    observed_at=None,
                    source_url="https://finance.sina.com.cn/fund/",
                    metadata={
                        "top": top_label,
                        "ranking": [metrics[c]["label"] for c in ranked],
                        "all_negative_momentum": all_negative,
                        "data_quality": "sina_hist_dividend",
                    },
                )
            )
            for code in ranked[:3]:
                item = metrics[code]
                signals.append(
                    MacroSignal(
                        source=self.provider_id,
                        signal_type="dividend_etf_metrics",
                        value=item["momentum_60d"],
                        interpretation=(
                            f"{item['label']}：最新价{item['price']:.3f}，60日动量{item['momentum_60d']:+.1f}%，"
                            f"年度分红约{item['annual_dividend']:.4f}元/份，股息率约{item['yield_pct']:.2f}%。"
                        ),
                        time_horizon="monthly",
                        confidence=0.65,
                        observed_at=None,
                        source_url="https://finance.sina.com.cn/fund/",
                        metadata={"etf": item["label"], "yield_pct": item["yield_pct"], "momentum_60d": item["momentum_60d"]},
                    )
                )
        else:
            for sina_code, item in metrics.items():
                signals.append(
                    MacroSignal(
                        source=self.provider_id,
                        signal_type="dividend_etf_metrics",
                        value=item["momentum_60d"],
                        interpretation=(
                            f"{item['label']}：最新价{item['price']:.3f}，60日动量{item['momentum_60d']:+.1f}%，"
                            "股息率数据不足（分红记录缺失）。"
                        ),
                        time_horizon="monthly",
                        confidence=0.6,
                        observed_at=None,
                        source_url="https://finance.sina.com.cn/fund/",
                        metadata={"etf": item["label"], "yield_pct": None, "momentum_60d": item["momentum_60d"]},
                    )
                )
        with _LOCK:
            _CACHE[cache_key] = (time.monotonic(), signals)
        return signals[:5]
