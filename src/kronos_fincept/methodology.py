"""Methodology rule engine: fox-finance technical rules + Dingning PR valuation.

All outputs are *facts* (rule status rows) intended for the LLM context and the
frontend evidence card. Nothing here replaces, matches, or constrains LLM
output; missing data is always reported as ``missing`` instead of invented.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import datetime
from datetime import date as _date
from typing import Any

logger = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value in {"", "-", "--", "None", "nan", "NaN"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _last(values: list[float] | None) -> float | None:
    if not values:
        return None
    return values[-1]


def _ema(closes: list[float], period: int) -> list[float] | None:
    if len(closes) < period:
        return None
    try:
        from kronos_fincept.financial import TechnicalIndicators

        values = TechnicalIndicators().calculate_ema(closes, period).values
        return [float(v) for v in values]
    except Exception as exc:  # pragma: no cover - defensive numeric path
        logger.debug("EMA(%s) failed: %s", period, exc)
        return None


def _rule(rule_id: str, name: str, status: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": rule_id,
        "name": name,
        "status": status if status in {"ok", "missing", "n/a"} else "missing",
        "detail": detail,
        "evidence": evidence or {},
    }


def _kline_rows(asset: dict[str, Any]) -> list[dict[str, Any]]:
    return (asset.get("market_data") or {}).get("rows") or []


def compute_fox_rules(asset: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute fox-finance technical rule rows from the asset's daily rows."""
    rows = _kline_rows(asset)
    if not rows:
        return [_rule("kline_data", "K线数据", "missing", "无K线数据，无法计算技术规则。")]
    closes = [_num(row.get("close")) for row in rows]
    closes = [value for value in closes if value is not None]
    if len(closes) < 30:
        return [_rule("kline_data", "K线数据", "missing", "K线样本不足（<30根），无法计算技术规则。")]

    price = closes[-1]
    highs = [_num(row.get("high")) for row in rows]
    lows = [_num(row.get("low")) for row in rows]
    volumes = [_num(row.get("volume")) for row in rows]
    amounts = [_num(row.get("amount")) for row in rows]
    rules: list[dict[str, Any]] = []

    # ── EMA tunnels ──
    ema_144 = _ema(closes, 144)
    ema_169 = _ema(closes, 169)
    if ema_144 and ema_169:
        e144, e169 = ema_144[-1], ema_169[-1]
        if price >= min(e144, e169):
            position = "价格位于1号隧道（EMA144/169）上方"
        elif price <= max(e144, e169):
            position = "价格位于1号隧道（EMA144/169）下方"
        else:
            position = "价格位于1号隧道（EMA144/169）内部"
        slope = "隧道上行" if e144 >= e169 else "隧道下行"
        rules.append(
            _rule(
                "ema_tunnel_1",
                "1号EMA隧道 (144/169)",
                "ok",
                f"{position}，{slope}（EMA144={e144:.2f}，EMA169={e169:.2f}）。",
                {"ema_144": round(e144, 4), "ema_169": round(e169, 4), "price": round(price, 4)},
            )
        )
    else:
        rules.append(_rule("ema_tunnel_1", "1号EMA隧道 (144/169)", "missing", "样本不足169根，1号隧道无法计算。"))

    ema_288 = _ema(closes, 288)
    ema_338 = _ema(closes, 338)
    if ema_288 and ema_338:
        e288, e338 = ema_288[-1], ema_338[-1]
        if price >= min(e288, e338):
            position = "价格位于2号隧道（EMA288/338）上方"
        elif price <= max(e288, e338):
            position = "价格位于2号隧道（EMA288/338）下方"
        else:
            position = "价格位于2号隧道（EMA288/338）内部"
        slope = "隧道上行" if e288 >= e338 else "隧道下行"
        rules.append(
            _rule(
                "ema_tunnel_2",
                "2号EMA隧道 (288/338)",
                "ok",
                f"{position}，{slope}（EMA288={e288:.2f}，EMA338={e338:.2f}）。",
                {"ema_288": round(e288, 4), "ema_338": round(e338, 4), "price": round(price, 4)},
            )
        )
    else:
        rules.append(_rule("ema_tunnel_2", "2号EMA隧道 (288/338)", "missing", "样本不足338根，2号隧道无法计算。"))

    # ── Fast EMA alignment ──
    fast_periods = (8, 13, 21, 55, 83)
    fast_emas = {period: _ema(closes, period) for period in fast_periods}
    if all(fast_emas[period] for period in fast_periods):
        last_values = [fast_emas[period][-1] for period in fast_periods]
        aligned_up = last_values == sorted(last_values, reverse=True)
        aligned_down = last_values == sorted(last_values)
        state = "多头排列（EMA8>13>21>55>83）" if aligned_up else "空头排列（EMA8<13<21<55<83）" if aligned_down else "均线交错，未形成单边排列"
        fast_cross = "EMA13上穿EMA21" if fast_emas[13][-1] >= fast_emas[21][-1] and fast_emas[13][-2] < fast_emas[21][-2] else (
            "EMA13下穿EMA21" if fast_emas[13][-1] <= fast_emas[21][-1] and fast_emas[13][-2] > fast_emas[21][-2] else "EMA13/21未发生交叉"
        )
        rules.append(
            _rule(
                "ema_fast_alignment",
                "EMA8/13/21/55/83 排列",
                "ok",
                f"{state}；{fast_cross}。",
                {f"ema_{period}": round(fast_emas[period][-1], 4) for period in fast_periods},
            )
        )
    else:
        rules.append(_rule("ema_fast_alignment", "EMA8/13/21/55/83 排列", "missing", "样本不足83根，快速均线排列无法计算。"))

    # ── KDJ regime ──
    try:
        from kronos_fincept.financial import TechnicalIndicators

        if highs and lows and all(value is not None for value in highs[-9:]) and all(value is not None for value in lows[-9:]):
            kdj = TechnicalIndicators().calculate_kdj([float(v) for v in highs], [float(v) for v in lows], closes)
            k, d, j = kdj.k[-1], kdj.d[-1], kdj.j[-1]
            flags = []
            if k >= 80 or j >= 100:
                flags.append("超买（K≥80/J≥100）")
            if k <= 20 or j <= 0:
                flags.append("超卖（K≤20/J≤0）")
            cross = "金叉" if kdj.k[-1] >= kdj.d[-1] and kdj.k[-2] < kdj.d[-2] else (
                "死叉" if kdj.k[-1] <= kdj.d[-1] and kdj.k[-2] > kdj.d[-2] else "未交叉"
            )
            state = "；".join(flags) if flags else "中性区间"
            rules.append(
                _rule(
                    "kdj_regime",
                    "KDJ 阈值",
                    "ok",
                    f"K={k:.2f} D={d:.2f} J={j:.2f}，{state}，最近{cross}。",
                    {"k": round(k, 4), "d": round(d, 4), "j": round(j, 4), "cross": cross},
                )
            )
        else:
            rules.append(_rule("kdj_regime", "KDJ 阈值", "missing", "缺少有效最高/最低价，KDJ无法计算。"))
    except Exception as exc:  # pragma: no cover - defensive numeric path
        rules.append(_rule("kdj_regime", "KDJ 阈值", "missing", f"KDJ计算失败：{exc}"))

    # ── MACD zero-axis state ──
    try:
        from kronos_fincept.financial import TechnicalIndicators

        macd = TechnicalIndicators().calculate_macd(closes)
        if macd.macd_line and macd.signal_line:
            m, s = macd.macd_line[-1], macd.signal_line[-1]
            zone = "零轴上方" if m >= 0 else "零轴下方"
            cross = "金叉" if m >= s and macd.macd_line[-2] < macd.signal_line[-2] else (
                "死叉" if m <= s and macd.macd_line[-2] > macd.signal_line[-2] else "未交叉"
            )
            rules.append(
                _rule(
                    "macd_zero_axis",
                    "MACD 零轴状态",
                    "ok",
                    f"MACD位于{zone}（MACD={m:.3f}），最近{cross}（信号线{s:.3f}）。",
                    {"macd": round(m, 6), "signal": round(s, 6), "zone": zone, "cross": cross},
                )
            )
        else:
            rules.append(_rule("macd_zero_axis", "MACD 零轴状态", "missing", "MACD序列不足，无法计算。"))
    except Exception as exc:  # pragma: no cover - defensive numeric path
        rules.append(_rule("macd_zero_axis", "MACD 零轴状态", "missing", f"MACD计算失败：{exc}"))

    # ── Fibonacci retracement (250-day wick high/low) ──
    window = min(250, len(closes))
    high_250 = max(value for value in highs[-window:] if value is not None) if any(value is not None for value in highs[-window:]) else None
    low_250 = min(value for value in lows[-window:] if value is not None) if any(value is not None for value in lows[-window:]) else None
    if high_250 and low_250 and high_250 > low_250:
        span = high_250 - low_250
        f382, f50, f618 = high_250 - span * 0.382, high_250 - span * 0.5, high_250 - span * 0.618
        if price >= f618:
            fib_state = "位于0.618上方（趋势偏强）"
        elif price >= f50:
            fib_state = "位于0.5-0.618之间（回撤中段）"
        elif price >= f382:
            fib_state = "位于0.382-0.5之间（回撤偏深）"
        else:
            fib_state = "跌破0.382（国内资产牛市结构关键位失守）"
        rules.append(
            _rule(
                "fibonacci_levels",
                "斐波那契回撤位",
                "ok",
                f"近{window}日高点{high_250:.2f}、低点{low_250:.2f}；0.618={f618:.2f}，0.5={f50:.2f}，0.382={f382:.2f}；现价{fib_state}。",
                {"high": round(high_250, 4), "low": round(low_250, 4), "f_382": round(f382, 4), "f_50": round(f50, 4), "f_618": round(f618, 4)},
            )
        )
    else:
        rules.append(_rule("fibonacci_levels", "斐波那契回撤位", "missing", "缺少有效最高/最低价，无法计算回撤位。"))

    # ── Volume/amount resonance (last 5 bars) ──
    if len(rows) >= 6 and amounts and any(value is not None for value in amounts[-5:]):
        vol_ok = all(value is not None and value > 0 for value in volumes[-5:])
        amt_ok = all(value is not None and value > 0 for value in amounts[-5:])
        if vol_ok and amt_ok:
            up_days, synced, fake_up = 0, 0, 0
            for idx in range(-4, 0):
                price_up = closes[idx] >= closes[idx - 1]
                vol_up = volumes[idx] >= volumes[idx - 1]
                amt_up = amounts[idx] >= amounts[idx - 1]
                if price_up:
                    up_days += 1
                    if vol_up and amt_up:
                        synced += 1
                    elif vol_up and not amt_up:
                        fake_up += 1
            rules.append(
                _rule(
                    "volume_amount_resonance",
                    "量额共振",
                    "ok",
                    f"近5日上涨{up_days}天；量额同步放量{synced}天，放量但成交额未跟进的疑似假性K线{fake_up}天。",
                    {"up_days": up_days, "synced_days": synced, "fake_up_days": fake_up},
                )
            )
        else:
            rules.append(_rule("volume_amount_resonance", "量额共振", "missing", "成交量或成交额数据缺失，无法判断量额共振。"))
    else:
        rules.append(_rule("volume_amount_resonance", "量额共振", "missing", "样本或成交额数据不足，无法判断量额共振。"))

    # ── Weekly structure (resample daily to weekly) ──
    try:
        import pandas as pd

        frame = pd.DataFrame(
            [{"ts": row.get("timestamp"), "close": row.get("close")} for row in rows]
        )
        frame["ts"] = pd.to_datetime(frame["ts"], errors="coerce")
        frame = frame.dropna(subset=["ts", "close"]).set_index("ts").sort_index()
        weekly = frame["close"].astype(float).resample("W-FRI").last().dropna()
        if len(weekly) >= 3:
            diffs = weekly.diff().dropna()
            last2 = [diffs.iloc[-1], diffs.iloc[-2]]
            direction = "涨" if last2[0] > 0 else "跌" if last2[0] < 0 else "平"
            prev_direction = "涨" if last2[1] > 0 else "跌" if last2[1] < 0 else "平"
            wk_ma = float(weekly.rolling(20).mean().iloc[-1]) if len(weekly) >= 20 else None
            ma_text = f"，周收盘{'高于' if weekly.iloc[-1] >= wk_ma else '低于'}20周均线({wk_ma:.2f})" if wk_ma else ""
            rules.append(
                _rule(
                    "weekly_structure",
                    "周线结构",
                    "ok",
                    f"最近周K线方向：{prev_direction}→{direction}；周收盘{weekly.iloc[-1]:.2f}{ma_text}。",
                    {"last_week": round(float(weekly.iloc[-1]), 4), "prev_week": round(float(weekly.iloc[-2]), 4)},
                )
            )
        else:
            rules.append(_rule("weekly_structure", "周线结构", "missing", "周线样本不足（<3周），无法判断周线结构。"))
    except Exception as exc:  # pragma: no cover - defensive path
        rules.append(_rule("weekly_structure", "周线结构", "missing", f"周线聚合失败：{exc}"))

    # ── Risk veto flags (facts only, never output restrictions) ──
    active: list[str] = []
    if ema_144 and ema_169 and price < min(ema_144[-1], ema_169[-1]):
        active.append("价格跌破1号隧道（EMA144/169）")
    if ema_288 and ema_338 and price < min(ema_288[-1], ema_338[-1]):
        active.append("价格跌破2号隧道（EMA288/338）")
    ema_55 = fast_emas.get(55)
    rsi = None
    try:
        from kronos_fincept.financial import TechnicalIndicators

        rsi = TechnicalIndicators().calculate_rsi(closes, 14).values[-1] if len(closes) >= 15 else None
    except Exception:
        rsi = None
    if ema_55 and rsi is not None and (price / ema_55[-1] - 1) > 0.15 and rsi >= 80:
        active.append("偏离EMA55超15%且RSI≥80，疑似抛物线末端")
    high_52w = max(closes[-250:]) if len(closes) >= 50 else max(closes)
    if high_52w and price >= high_52w * 0.98:
        active.append("贴近52周高点（≥98%），上方压力显著")
    rules.append(
        _rule(
            "risk_veto",
            "财道风险否决清单",
            "ok",
            "；".join(active) if active else "未命中风险否决项。",
            {"flags": active},
        )
    )

    # ── Support/resistance levels ──
    if high_52w and low_250:
        rules.append(
            _rule(
                "support_resistance",
                "支撑/压力位",
                "ok",
                f"近52周高点{high_52w:.2f}、低点{low_250:.2f}；斐波那契0.5回撤位约{high_52w - (high_52w - low_250) * 0.5:.2f}。",
                {"high_52w": round(high_52w, 4), "low_250": round(low_250, 4)},
            )
        )
    else:
        rules.append(_rule("support_resistance", "支撑/压力位", "missing", "高低点数据缺失，无法给出支撑/压力位。"))

    return rules


# ── PR valuation (Dingning 市赚率) ──

_valuation_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_valuation_lock = threading.Lock()
_VALUATION_TTL_SECONDS = 30 * 60


def _cached_valuation(key: str) -> dict[str, Any] | None:
    with _valuation_lock:
        entry = _valuation_cache.get(key)
        if entry and time.monotonic() - entry[0] < _VALUATION_TTL_SECONDS:
            return entry[1]
    return None


def _set_valuation_cache(key: str, value: dict[str, Any]) -> None:
    with _valuation_lock:
        _valuation_cache[key] = (time.monotonic(), value)


def _fetch_cn_valuation(symbol: str) -> dict[str, Any]:
    cache_key = f"cn:{symbol}"
    cached = _cached_valuation(cache_key)
    if cached is not None:
        return cached
    out: dict[str, Any] = {}
    try:
        # Baidu valuation series (pe_ttm/pb) — no Tushare per-minute rate limit.
        import akshare as ak

        pe_frame = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市盈率(TTM)")
        if pe_frame is not None and not pe_frame.empty:
            pe = _num(pe_frame.iloc[-1].get("value"))
            if pe is not None:
                out["pe"] = pe
                out["pe_ttm"] = pe
        pb_frame = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市净率")
        if pb_frame is not None and not pb_frame.empty:
            pb = _num(pb_frame.iloc[-1].get("value"))
            if pb is not None:
                out["pb"] = pb
    except Exception as exc:
        logger.debug("[methodology] CN baidu valuation failed for %s: %s", symbol, exc)
    try:
        import akshare as ak

        frame = ak.stock_financial_analysis_indicator(symbol=symbol, start_year=str(datetime.now().year - 1))
        if frame is not None and not frame.empty:
            roe = _cn_annualized_roe(frame)
            payout = None
            for _, row in frame.iterrows():
                value = _num(row.get("股息发放率(%)"))
                if value is not None:
                    payout = value / 100.0
            if roe is not None:
                out["roe"] = roe
            if payout is not None:
                out["payout_ratio"] = payout
    except Exception as exc:
        logger.debug("[methodology] CN financial indicator failed for %s: %s", symbol, exc)
    _set_valuation_cache(cache_key, out)
    return out


def _cn_annualized_roe(frame: Any) -> float | None:
    """Return an annualized ROE from AkShare's year-to-date cumulative values.

    The indicator is cumulative within each fiscal year (Q1 ~10%, H1 ~19%,
    Q3 ~25%, FY ~35%). Prefer the most recent annual (12-31) report; otherwise
    annualize the latest cumulative value by quarter multiplier.
    """
    latest_annual: float | None = None
    latest_cumulative: tuple[_date, float] | None = None
    quarter_multiplier = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}
    for _, row in frame.iterrows():
        raw_date = row.get("日期")
        try:
            if isinstance(raw_date, _date):
                report_date = raw_date
            else:
                report_date = datetime.fromisoformat(str(raw_date)[:10]).date()
        except (TypeError, ValueError):
            continue
        roe = _num(row.get("净资产收益率(%)"))
        if roe is None:
            continue
        roe_fraction = roe / 100.0
        if report_date.month == 12:
            latest_annual = roe_fraction
        multiplier = quarter_multiplier.get(report_date.month)
        if multiplier is not None:
            latest_cumulative = (report_date, roe_fraction * multiplier)
    if latest_annual is not None:
        return latest_annual
    if latest_cumulative is not None:
        return latest_cumulative[1]
    return None


def _fetch_hk_valuation(symbol: str) -> dict[str, Any]:
    cache_key = f"hk:{symbol}"
    cached = _cached_valuation(cache_key)
    if cached is not None:
        return cached
    out: dict[str, Any] = {}
    try:
        import akshare as ak

        code = str(symbol).strip().upper().removesuffix(".HK")
        if not re.fullmatch(r"\d{5}", code):
            code = code.zfill(5)
        frame = ak.stock_hk_financial_indicator_em(symbol=code)
        if frame is not None and not frame.empty:
            last = frame.iloc[-1]
            pe = _num(last.get("市盈率"))
            pb = _num(last.get("市净率"))
            roe = _num(last.get("股东权益回报率(%)"))
            dv = _num(last.get("股息率TTM(%)"))
            payout = _num(last.get("派息比率(%)"))
            market_cap = _num(last.get("总市值(港元)"))
            if pe is not None:
                out["pe"] = pe
            if pb is not None:
                out["pb"] = pb
            if roe is not None:
                normalized_roe = roe / 100.0
                # HK snapshots often report quarterly ROE (~5% for high-ROE
                # names); annualize when the value looks like a single quarter.
                if roe < 8.0:
                    normalized_roe *= 4.0
                    out["roe_normalized"] = "quarterly_annualized"
                out["roe"] = normalized_roe
            if dv is not None:
                out["dv_ratio"] = dv
            if payout is not None:
                out["payout_ratio"] = payout / 100.0
            if market_cap is not None:
                out["market_cap"] = market_cap
    except Exception as exc:
        logger.debug("[methodology] HK valuation failed for %s: %s", symbol, exc)
    _set_valuation_cache(cache_key, out)
    return out


def _pr_band(pr: float) -> str:
    if pr < 0.4:
        return "4折极低估区"
    if pr < 0.5:
        return "5折好球区（巴菲特式）"
    if pr < 0.6:
        return "6折分批/轻仓试探区"
    if pr < 0.8:
        return "0.7-0.8PR 观察/定投区"
    if pr <= 1.0:
        return "接近1PR 合理区"
    return "≥1PR 合理到高估区"


def compute_pr_valuation(asset: dict[str, Any], financial_data: dict[str, Any] | None) -> dict[str, Any]:
    """Compute Dingning PR valuation rows for one asset (facts only)."""
    asset_class = str(asset.get("asset_class") or "equity")
    market = str(asset.get("market") or "").lower()
    symbol = str(asset.get("symbol") or "")
    if asset_class in {"commodity_future", "etf"}:
        reason = (
            "商品期货不适用市赚率估值；优先使用价格趋势、波动风险、持仓/利率等信号。"
            if asset_class == "commodity_future"
            else "ETF/基金不适用单一公司市赚率估值；指数级估值可在宏观洞察页查看。"
        )
        return {
            "status": "n/a",
            "formula": None,
            "inputs": {},
            "pr": None,
            "corrected_pr": None,
            "band": None,
            "tax_note": None,
            "missing_reasons": [reason],
            "detail": reason,
        }

    data = dict(financial_data or {})
    fetched: dict[str, Any] = {}
    if market == "cn" and symbol:
        fetched = _fetch_cn_valuation(symbol)
    elif market == "hk" and symbol:
        fetched = _fetch_hk_valuation(symbol)
    data.update(fetched)

    pe = _num(data.get("pe_ttm") or data.get("pe"))
    pb = _num(data.get("pb"))
    roe = _num(data.get("roe"))
    payout = _num(data.get("payout_ratio"))
    dv = _num(data.get("dv_ratio"))

    inputs: dict[str, Any] = {}
    for key in ("pe", "pe_ttm", "pb", "roe", "dv_ratio", "payout_ratio", "revenue", "net_income", "gross_profit", "market_cap", "period"):
        value = data.get(key)
        if value is not None:
            inputs[key] = round(float(value), 6) if isinstance(value, (int, float)) else value

    missing: list[str] = []
    if pe is None or pe <= 0:
        missing.append("PE缺失或非正")
    if pb is None or pb <= 0:
        missing.append("PB缺失或非正")
    if roe is None:
        missing.append("ROE缺失")
    if len(missing) >= 2:
        return {
            "status": "missing",
            "formula": None,
            "inputs": inputs,
            "pr": None,
            "corrected_pr": None,
            "band": None,
            "tax_note": "港股股息税约20%，合理PR阈值按0.8折算。" if market == "hk" else None,
            "missing_reasons": missing,
            "detail": "；".join(missing) + "，无法计算市赚率。",
        }

    f1 = (pe / (roe * 100.0)) if (roe is not None and roe > 0) else None
    f3 = (pe * pe / (pb * 100.0)) if (pb is not None and pb > 0) else None
    primary = f1 if f1 is not None else f3
    formula = (
        "F1: PE/(ROE×100)"
        if f1 is not None
        else "F3: PE²/(PB×100)（ROE不可用时的备选公式）"
    )
    corrected = None
    if f1 is not None and payout is not None and payout > 0:
        corrected = f1 * (0.5 / payout)
    band = _pr_band(primary) if primary is not None else None
    tax_note = "港股股息税约20%，合理PR阈值按0.8折算。" if market == "hk" else None

    detail_parts = [f"市赚率PR={primary:.3f}" if primary is not None else "PR无法计算"]
    if corrected is not None:
        detail_parts.append(f"按派息率{payout * 100:.1f}%修正为PR'={corrected:.3f}")
    elif f1 is not None:
        detail_parts.append("派息率缺失，未做分红率修正")
    if isinstance(data.get("roe_normalized"), str):
        detail_parts.append("ROE按季度数据年化处理")
    if band:
        detail_parts.append(f"处于{band}")
    detail_parts.append("（估值便宜≠可买，技术面负责择时）")
    if tax_note:
        detail_parts.append(tax_note)
    if dv is not None:
        detail_parts.append(f"股息率TTM约{dv:.2f}%")

    return {
        "status": "ok" if primary is not None else "missing",
        "formula": formula,
        "inputs": inputs,
        "pr": round(primary, 6) if primary is not None else None,
        "pr_f3": round(f3, 6) if f3 is not None else None,
        "corrected_pr": round(corrected, 6) if corrected is not None else None,
        "band": band,
        "tax_note": tax_note,
        "missing_reasons": missing,
        "detail": "；".join(detail_parts),
    }


def compute_methodology(asset: dict[str, Any]) -> dict[str, Any]:
    """Compute the full methodology block for one asset."""
    return {
        "rules": compute_fox_rules(asset),
        "pr": compute_pr_valuation(asset, asset.get("financial_data")),
    }


def compact_methodology_for_llm(value: Any) -> Any:
    """Compact methodology facts for LLM context (truncate long evidence)."""
    if not isinstance(value, dict):
        return value
    rules = value.get("rules") or []
    compact_rules = [
        {
            "id": rule.get("id"),
            "name": rule.get("name"),
            "status": rule.get("status"),
            "detail": str(rule.get("detail") or "")[:240],
        }
        for rule in rules[:12]
        if isinstance(rule, dict)
    ]
    pr = value.get("pr") or {}
    compact_pr = {key: pr.get(key) for key in ("status", "formula", "pr", "pr_f3", "corrected_pr", "band", "tax_note", "missing_reasons", "detail") if pr.get(key) is not None}
    if isinstance(compact_pr.get("detail"), str):
        compact_pr["detail"] = compact_pr["detail"][:300]
    return {"rules": compact_rules, "pr": compact_pr}
