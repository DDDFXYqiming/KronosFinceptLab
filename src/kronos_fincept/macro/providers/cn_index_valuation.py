"""CN index valuation provider (A-share index PE/PB percentile + dividend yield).

Sources:
- 乐咕乐股 (legulegu) long history via akshare ``stock_index_pe_lg`` /
  ``stock_index_pb_lg`` for 沪深300 / 上证50 / 上证红利 (5y percentile).
- 中证指数官网 snapshot via ``stock_zh_index_value_csindex`` for 中证红利.

Outputs are valuation facts (PE/PB percentile, dividend yield) for the LLM;
they never constrain macro conclusions directly.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

logger = logging.getLogger(__name__)


RELEVANCE_PATTERN = re.compile(
    r"估值|贵不贵|便宜|贵了|红利|股息|分红|市盈率|市净率|PE|PB|大盘|指数|沪深|上证|深证|创业板|中证|配置时机|定投|高股息",
    re.IGNORECASE,
)

_PE_INDEXES = ("沪深300", "上证50", "上证红利")
_CACHE: dict[str, tuple[float, list[MacroSignal]]] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 30 * 60


def _relevant(query: MacroQuery) -> bool:
    text = " ".join(
        part for part in (query.question or "", " ".join(query.symbols or ()), query.market or "") if part
    )
    return bool(RELEVANCE_PATTERN.search(text))


def _percentile(value: float, series: list[float]) -> float:
    if not series:
        return 0.5
    below = sum(1 for item in series if item <= value)
    return below / len(series)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _five_year_rows(frame: Any) -> list[dict[str, Any]]:
    """Return rows within the last ~5 years, newest last."""
    if frame is None or getattr(frame, "empty", True):
        return []
    cutoff = datetime.now() - timedelta(days=365 * 5)
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        date_value = record.get("日期")
        try:
            ts = date_value if isinstance(date_value, datetime) else datetime.fromisoformat(str(date_value)[:10])
        except (TypeError, ValueError):
            continue
        if ts >= cutoff:
            rows.append(record)
    return rows


class CnIndexValuationProvider(MacroProvider):
    provider_id = "cn_index_valuation"
    display_name = "指数估值 (乐咕/中证)"
    capabilities = ("valuation", "index", "dividend", "equity")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _relevant(query):
            return []
        cache_key = query.cache_key()
        with _LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _TTL_SECONDS:
                return cached[1]
        signals: list[MacroSignal] = []
        try:
            import akshare as ak

            for index_name in _PE_INDEXES:
                try:
                    pe_frame = ak.stock_index_pe_lg(symbol=index_name)
                    pb_frame = ak.stock_index_pb_lg(symbol=index_name)
                    pe_rows = _five_year_rows(pe_frame)
                    pb_rows = _five_year_rows(pb_frame)
                    if not pe_rows or not pb_rows:
                        continue
                    pe_current = _number(pe_rows[-1].get("滚动市盈率"))
                    pb_current = _number(pb_rows[-1].get("市净率"))
                    if pe_current is None or pb_current is None:
                        continue
                    pe_series = [v for v in (_number(row.get("滚动市盈率")) for row in pe_rows) if v is not None]
                    pb_series = [v for v in (_number(row.get("市净率")) for row in pb_rows) if v is not None]
                    pe_pct = _percentile(pe_current, pe_series)
                    pb_pct = _percentile(pb_current, pb_series)
                    signals.append(
                        MacroSignal(
                            source=self.provider_id,
                            signal_type="cn_index_valuation",
                            value=round(pe_pct, 3),
                            interpretation=(
                                f"{index_name}：滚动PE={pe_current:.1f}（近5年分位{pe_pct * 100:.0f}%），"
                                f"PB={pb_current:.2f}（近5年分位{pb_pct * 100:.0f}%）；"
                                f"{'估值偏高' if pe_pct >= 0.8 else '估值偏低' if pe_pct <= 0.2 else '估值中性'}。"
                            ),
                            time_horizon="monthly",
                            confidence=0.75,
                            observed_at=str(pe_rows[-1].get("日期"))[:10],
                            source_url="https://legulegu.com/stockdata/index-basic-pe",
                            metadata={"index": index_name, "pe_percentile": round(pe_pct, 4), "pb_percentile": round(pb_pct, 4), "data_quality": "legulegu_history"},
                        )
                    )
                except Exception as exc:
                    logger.debug("[cn_index_valuation] %s failed: %s", index_name, exc)

            try:
                csindex = ak.stock_zh_index_value_csindex(symbol="000922")
                if csindex is not None and not csindex.empty:
                    last = csindex.iloc[-1]
                    pe_1 = _number(last.get("市盈率1"))
                    dy_1 = _number(last.get("股息率1"))
                    if pe_1 is not None:
                        signals.append(
                            MacroSignal(
                                source=self.provider_id,
                                signal_type="cn_index_dividend_yield",
                                value=round(dy_1, 3) if dy_1 is not None else None,
                                interpretation=(
                                    f"中证红利：市盈率{pe_1:.2f}，股息率{ddy:.2f}%（中证指数官方快照）。"
                                    if (ddy := dy_1) is not None
                                    else f"中证红利：市盈率{pe_1:.2f}（股息率缺失）。"
                                ),
                                time_horizon="monthly",
                                confidence=0.7,
                                observed_at=str(last.get("日期"))[:10],
                                source_url="https://www.csindex.com.cn/",
                                metadata={"index": "中证红利", "pe": round(pe_1, 4), "dividend_yield": round(dy_1, 4) if dy_1 is not None else None, "data_quality": "csindex_snapshot"},
                            )
                        )
            except Exception as exc:
                logger.debug("[cn_index_valuation] csindex failed: %s", exc)
        except Exception as exc:
            logger.warning("[cn_index_valuation] provider failure: %s", exc)
        with _LOCK:
            _CACHE[cache_key] = (time.monotonic(), signals)
        return signals[:5]
