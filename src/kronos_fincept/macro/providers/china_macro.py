"""China macro provider backed by AkShare."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderUnavailable
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal


class ChinaMacroAkshareProvider(MacroProvider):
    provider_id = "china_macro_akshare"
    display_name = "China Macro (AkShare)"
    capabilities = ("china_macro", "pmi", "inflation", "rates", "liquidity")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _query_relevant(query):
            return []
        try:
            import akshare as ak
        except ImportError as exc:
            raise MacroProviderUnavailable("akshare is not installed") from exc

        indicators = _select_indicators(query)
        signals: list[MacroSignal] = []
        # 并发调用各指标 fetcher，避免串行累积超过 provider timeout
        # (单个接口约 1-6s，5 个串行可达 20s+ 触发 12s 超时；并发后总耗时 ≈ 最慢单个)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_one(indicator: str):
            fetcher = getattr(self, f"_fetch_{indicator}", None)
            if fetcher is None:
                return indicator, None
            try:
                return indicator, _with_timeout(fetcher, 10, ak)
            except Exception:
                return indicator, None

        with ThreadPoolExecutor(max_workers=min(len(indicators), 5)) as executor:
            futures = [executor.submit(_run_one, ind) for ind in indicators]
            for future in as_completed(futures):
                indicator, frame = future.result()
                if frame is None:
                    continue
                signal = _frame_to_signal(indicator, frame)
                if signal is not None:
                    signals.append(signal)
        return signals

    def _fetch_pmi(self, ak: Any) -> Any:
        frame = ak.macro_china_pmi()
        date_col = _find_column(frame, ["月份", "日期"])
        value_col = _find_column(frame, ["制造业-指数", "PMI", "pmi"], exclude=["同比", "增长"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_cpi_yoy(self, ak: Any) -> Any:
        frame = ak.macro_china_cpi()
        date_col = _find_column(frame, ["月份", "日期"])
        value_col = _find_column(frame, ["全国-同比增长", "全国-同比"], exclude=["累计", "环比"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_ppi_yoy(self, ak: Any) -> Any:
        frame = ak.macro_china_ppi_yearly()
        date_col = _find_column(frame, ["日期", "月份"])
        value_col = _find_column(frame, ["全部工业", "同比", "今值"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_lpr_1y(self, ak: Any) -> Any:
        frame = ak.macro_china_lpr()
        date_col = _find_column(frame, ["日期", "TRADE_DATE"])
        value_col = _find_column(frame, ["1年期", "LPR", "LPR1Y"], exclude=["5年"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_bond_10y(self, ak: Any) -> Any:
        frame = ak.bond_zh_us_rate()
        date_col = _find_column(frame, ["日期"])
        value_col = _find_column(frame, ["中国国债收益率10年", "中国10年", "10年"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_gdp(self, ak: Any) -> Any:
        frame = ak.macro_china_gdp()
        date_col = _find_column(frame, ["季度", "日期"])
        value_col = _find_column(frame, ["国内生产总值-同比增长", "当季同比", "同比增长"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_social_financing_yoy(self, ak: Any) -> Any:
        frame = ak.macro_china_bank_financing()
        date_col = _find_column(frame, ["日期", "月份"])
        value_col = _find_column(frame, ["近1年涨跌幅", "1年涨跌幅", "同比", "增速", "增长"])
        return _standard_frame(frame, date_col, value_col)

    def _fetch_m1_m2(self, ak: Any) -> Any:
        import pandas as pd

        frame = ak.macro_china_money_supply()
        date_col = _find_column(frame, ["月份", "日期"])
        m1_col = _find_column(frame, ["货币(M1)-同比增长", "M1"])
        m2_col = _find_column(frame, ["货币和准货币(M2)-同比增长", "M2"])
        if frame is None or frame.empty or not date_col or not m1_col or not m2_col:
            return pd.DataFrame()
        result = pd.DataFrame(
            {
                "date": frame[date_col].map(_parse_date),
                "m1_value": pd.to_numeric(frame[m1_col], errors="coerce"),
                "m2_value": pd.to_numeric(frame[m2_col], errors="coerce"),
            }
        )
        result["value"] = result["m1_value"] - result["m2_value"]
        return result.dropna(subset=["date", "value"]).sort_values("date").reset_index(drop=True)


INDICATOR_META = {
    "pmi": ("China manufacturing PMI", "growth", "PMI is a timely manufacturing cycle gauge."),
    "cpi_yoy": ("China CPI YoY", "inflation", "CPI YoY tracks consumer inflation pressure."),
    "ppi_yoy": ("China PPI YoY", "inflation", "PPI YoY tracks upstream industrial price pressure."),
    "lpr_1y": ("China 1Y LPR", "rates", "1Y LPR is a key credit-pricing benchmark."),
    "bond_10y": ("China 10Y government bond yield", "rates", "China 10Y yield reflects domestic rate expectations."),
    "gdp": ("China GDP YoY", "growth", "GDP YoY tracks broad growth momentum."),
    "social_financing_yoy": ("China social financing YoY", "liquidity", "Social financing tracks credit impulse."),
    "m1_m2": ("China M1-M2 spread", "liquidity", "M1-M2 spread tracks monetary activity mix."),
}


def _query_relevant(query: MacroQuery) -> bool:
    text = " ".join([query.question or "", " ".join(query.symbols), str(query.market or "")]).lower()
    if query.market == "cn":
        return True
    return bool(
        re.search(
            r"china|中国|a股|人民币|央行|pmi|cpi|ppi|lpr|社融|m1|m2|中债|国债|出口|消费|工业|gdp|增长",
            text,
            flags=re.IGNORECASE,
        )
    )


def _select_indicators(query: MacroQuery) -> list[str]:
    text = (query.question or "").lower()
    selected: list[str] = []

    def add(*items: str) -> None:
        for item in items:
            if item not in selected:
                selected.append(item)

    if re.search(r"pmi|制造业|景气", text, re.IGNORECASE):
        add("pmi")
    if re.search(r"cpi|通胀|物价|inflation", text, re.IGNORECASE):
        add("cpi_yoy", "ppi_yoy")
    if re.search(r"lpr|利率|收益率|国债|中债|央行|降息|加息", text, re.IGNORECASE):
        add("lpr_1y", "bond_10y")
    if re.search(r"社融|信用|m1|m2|货币|流动性", text, re.IGNORECASE):
        add("social_financing_yoy", "m1_m2")
    if re.search(r"gdp|增长|经济", text, re.IGNORECASE):
        add("gdp")
    if not selected:
        add("pmi", "cpi_yoy", "ppi_yoy", "lpr_1y", "bond_10y")
    return selected[: max(1, min(query.limit or 5, 6))]


def _with_timeout(func: Callable[..., Any], timeout: int, *args: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"China macro provider timed out after {timeout}s") from exc


def _standard_frame(frame: Any, date_col: str | None, value_col: str | None) -> Any:
    import pandas as pd

    if frame is None or frame.empty or not date_col or not value_col:
        return pd.DataFrame()
    result = pd.DataFrame(
        {
            "date": frame[date_col].map(_parse_date),
            "value": pd.to_numeric(frame[value_col], errors="coerce"),
        }
    )
    return result.dropna(subset=["date", "value"]).sort_values("date").reset_index(drop=True)


def _frame_to_signal(indicator: str, frame: Any) -> MacroSignal | None:
    if frame is None or frame.empty:
        return None
    row = frame.dropna(subset=["value"]).tail(1)
    if row.empty:
        return None
    item = row.iloc[0]
    label, signal_type, note = INDICATOR_META[indicator]
    observed = item.get("date")
    value = float(item.get("value"))
    return MacroSignal(
        source=ChinaMacroAkshareProvider.provider_id,
        signal_type=signal_type,
        value=value,
        interpretation=f"{label} latest value is {value:g}. {note}",
        time_horizon="mixed",
        confidence=0.68,
        observed_at=observed.date().isoformat() if hasattr(observed, "date") else str(observed),
        source_url="https://akshare.akfamily.xyz/",
        metadata={
            "indicator": indicator,
            "label": label,
            "data_quality": "akshare_china_macro",
        },
    )


def _find_column(frame: Any, keywords: list[str], exclude: list[str] | None = None) -> str | None:
    if frame is None or frame.empty:
        return None
    excludes = exclude or []
    for keyword in keywords:
        for column in frame.columns:
            text = str(column)
            if keyword in text and not any(item in text for item in excludes):
                return column
    return None


def _parse_date(value: Any) -> Any:
    import pandas as pd

    text = str(value).strip()
    match = re.match(r"(\d{4})年(\d{1,2})月份?", text)
    if match:
        return pd.Timestamp(year=int(match.group(1)), month=int(match.group(2)), day=1)
    match = re.match(r"(\d{4})年第?(\d)季度", text)
    if match:
        month = {1: 3, 2: 6, 3: 9, 4: 12}.get(int(match.group(2)), 12)
        return pd.Timestamp(year=int(match.group(1)), month=month, day=1)
    compact = text.replace("年", "-").replace("月", "").replace("日", "")
    return pd.to_datetime(compact, errors="coerce")
