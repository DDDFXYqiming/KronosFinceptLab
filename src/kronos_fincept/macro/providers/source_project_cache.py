"""Macro provider backed by the verified source project's local data cache."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderUnavailable
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal


DEFAULT_SOURCE_PROJECT = Path(r"E:\AI_Projects\------\Stock Analysis System")


def _series(
    file: str,
    label: str,
    signal_type: str,
    market: str,
    keywords: str = "",
    *,
    value_column: str = "value",
    priority: int = 50,
) -> dict[str, str | int]:
    return {
        "file": file,
        "label": label,
        "type": signal_type,
        "market": market,
        "keywords": keywords,
        "value_column": value_column,
        "priority": priority,
    }


CACHE_SERIES: dict[str, dict[str, str | int]] = {
    # China growth, inflation and policy.
    "china_gdp": _series("china_gdp.parquet", "China GDP YoY", "growth", "cn", "gdp|growth|中国|经济|增长", priority=1),
    "china_gdp_absolute": _series("china_gdp_absolute.parquet", "China GDP level", "growth", "cn", "gdp|规模|总量"),
    "china_pmi": _series("china_pmi.parquet", "China official manufacturing PMI", "growth", "cn", "pmi|制造业|景气", priority=3),
    "caixin_pmi": _series("caixin_pmi.parquet", "Caixin manufacturing PMI", "growth", "cn", "caixin|财新|pmi", priority=2),
    "china_non_man_pmi": _series("china_non_man_pmi.parquet", "China non-manufacturing PMI", "growth", "cn", "non manufacturing|非制造业|服务业|pmi"),
    "china_pmi_new_orders": _series("china_pmi_new_orders.parquet", "China PMI new orders", "growth", "cn", "new orders|新订单|pmi"),
    "china_bci": _series("china_bci.parquet", "China business climate index", "sentiment", "cn", "bci|景气|信心"),
    "china_cpi_yoy": _series("china_cpi_yoy.parquet", "China CPI YoY", "inflation", "cn", "cpi|inflation|通胀|物价", priority=2),
    "china_ppi_yoy": _series("china_ppi_yoy.parquet", "China PPI YoY", "inflation", "cn", "ppi|工业品|出厂价格"),
    "china_lpr_1y": _series("china_lpr_1y.parquet", "China 1Y LPR", "rates", "cn", "lpr|贷款市场报价|利率"),
    "china_lpr_5y": _series("china_lpr_5y.parquet", "China 5Y LPR", "rates", "cn", "lpr|五年|房贷|利率"),
    "china_lpr": _series("china_lpr.parquet", "China LPR composite", "rates", "cn", "lpr|贷款市场报价|利率"),
    "china_bond_1y": _series("china_bond_1y.parquet", "China 1Y bond yield", "rates", "cn", "1y|一年|国债|收益率"),
    "china_bond_5y": _series("china_bond_5y.parquet", "China 5Y bond yield", "rates", "cn", "5y|五年|国债|收益率"),
    "china_bond_10y": _series("china_bond_10y.parquet", "China 10Y bond yield", "rates", "cn", "10y|十年|国债|收益率", priority=3),
    "china_bond_30y": _series("china_bond_30y.parquet", "China 30Y bond yield", "rates", "cn", "30y|三十年|超长债|国债"),
    "cn_us_bond_spread": _series("cn_us_bond_spread.parquet", "China-US 10Y bond spread", "rates", "global", "中美利差|利差|spread|cn us"),
    "china_r007": _series("china_r007.parquet", "China R007 repo rate", "liquidity", "cn", "r007|回购|资金利率"),
    "china_shibor_overnight": _series("china_shibor_overnight.parquet", "China overnight SHIBOR", "liquidity", "cn", "shibor|隔夜|资金利率"),
    "china_omo_7d": _series("china_omo_7d.parquet", "China 7D OMO rate", "liquidity", "cn", "omo|逆回购|公开市场"),
    "china_slf_7d": _series("china_slf_7d.parquet", "China 7D SLF rate", "liquidity", "cn", "slf|常备借贷便利"),
    "central_bank_oml": _series("central_bank_oml.parquet", "China central bank OMO liquidity", "liquidity", "cn", "央行|公开市场|流动性"),
    "local_gov_bond": _series("local_gov_bond.parquet", "China local government bond issuance", "liquidity", "cn", "地方债|专项债"),
    # China activity, credit, housing and trade.
    "china_industrial_growth_yoy": _series("china_industrial_growth_yoy.parquet", "China industrial production YoY", "growth", "cn", "industrial|工业|生产"),
    "china_retail_sales_yoy": _series("china_retail_sales_yoy.parquet", "China retail sales YoY", "growth", "cn", "retail|消费|社零|零售"),
    "china_fai_yoy": _series("china_fai_yoy.parquet", "China fixed asset investment YoY", "growth", "cn", "fai|固定资产|投资"),
    "china_real_estate_investment_yoy": _series("china_real_estate_investment_yoy.parquet", "China real estate investment YoY", "housing", "cn", "real estate|房地产|地产|投资"),
    "china_house_price_index": _series("china_house_price_index.parquet", "China house price index", "housing", "cn", "house price|房价|地产"),
    "city_house_sales": _series("city_house_sales.parquet", "China city house sales", "housing", "cn", "house sales|楼市|成交|地产"),
    "china_industrial_profit": _series("china_industrial_profit.parquet", "China industrial profits", "profits", "cn", "industrial profit|工业利润"),
    "china_electricity": _series("china_electricity.parquet", "China electricity output", "growth", "cn", "electricity|用电|发电"),
    "car_retail_sales": _series("car_retail_sales.parquet", "China passenger car retail sales", "growth", "cn", "car|auto|汽车"),
    "excavator_sales": _series("excavator_sales.parquet", "China excavator sales", "growth", "cn", "excavator|挖掘机|基建"),
    "china_consumer_confidence": _series("china_consumer_confidence.parquet", "China consumer confidence", "sentiment", "cn", "consumer confidence|消费者信心"),
    "china_loan_yoy": _series("china_loan_yoy.parquet", "China RMB loan YoY", "credit", "cn", "loan|信贷|贷款"),
    "china_social_financing_yoy": _series("china_social_financing_yoy.parquet", "China social financing YoY", "credit", "cn", "social financing|社融|融资"),
    "china_social_financing_stock": _series("china_social_financing_stock.parquet", "China social financing stock", "credit", "cn", "social financing|社融|存量"),
    "china_m1_m2": _series("china_m1_m2.parquet", "China M1-M2 spread", "liquidity", "cn", "m1|m2|货币|剪刀差", value_column="spread"),
    "m2_supply": _series("m2_supply.parquet", "China M2 supply", "liquidity", "cn", "m2|货币供应"),
    "china_household_deposit": _series("china_household_deposit.parquet", "China household deposits", "liquidity", "cn", "deposit|储蓄|存款"),
    "china_savings_rate": _series("china_savings_rate.parquet", "China savings rate", "liquidity", "cn", "savings|储蓄率"),
    "china_forex_reserve": _series("china_forex_reserve.parquet", "China FX reserves", "liquidity", "cn", "forex|reserve|外汇|储备"),
    "china_unemployment_rate": _series("china_unemployment_rate.parquet", "China urban unemployment rate", "labor", "cn", "unemployment|失业"),
    "china_export_yoy": _series("china_export_yoy.parquet", "China export YoY", "trade", "cn", "export|出口|贸易"),
    "china_import_usd": _series("china_import_usd.parquet", "China imports USD", "trade", "cn", "import|进口|贸易"),
    "china_trade_total": _series("china_trade_total.parquet", "China total trade", "trade", "cn", "trade|进出口|贸易"),
    # NBS official and cnstats verified fallbacks.
    "nbs_v32_pmi": _series("nbs_v32_pmi.parquet", "NBS v3.2 PMI", "growth", "cn", "nbs|国家统计局|pmi|官方"),
    "nbs_v32_cpi_yoy": _series("nbs_v32_cpi_yoy.parquet", "NBS v3.2 CPI YoY", "inflation", "cn", "nbs|国家统计局|cpi|通胀"),
    "nbs_v32_ppi_yoy": _series("nbs_v32_ppi_yoy.parquet", "NBS v3.2 PPI YoY", "inflation", "cn", "nbs|国家统计局|ppi"),
    "cnstats_pmi": _series("cnstats_pmi.parquet", "CNStats PMI", "growth", "cn", "cnstats|pmi|官方"),
    "cnstats_cpi_yoy": _series("cnstats_cpi_yoy.parquet", "CNStats CPI YoY", "inflation", "cn", "cnstats|cpi"),
    "cnstats_ppi_yoy": _series("cnstats_ppi_yoy.parquet", "CNStats PPI YoY", "inflation", "cn", "cnstats|ppi"),
    "cnstats_m2_yoy": _series("cnstats_m2_yoy.parquet", "CNStats M2 YoY", "liquidity", "cn", "cnstats|m2|货币"),
    "cnstats_m2_level": _series("cnstats_m2_level.parquet", "CNStats M2 level", "liquidity", "cn", "cnstats|m2|货币"),
    "cnstats_fixed_investment_yoy": _series("cnstats_fixed_investment_yoy.parquet", "CNStats fixed investment YoY", "growth", "cn", "cnstats|固定资产|投资"),
    "cnstats_industrial_value_added_yoy": _series("cnstats_industrial_value_added_yoy.parquet", "CNStats industrial value added YoY", "growth", "cn", "cnstats|工业增加值"),
    "cnstats_retail_sales_yoy": _series("cnstats_retail_sales_yoy.parquet", "CNStats retail sales YoY", "growth", "cn", "cnstats|社零|零售"),
    # China market flow and risk appetite.
    "hsgt_north": _series("hsgt_north.parquet", "Northbound Stock Connect net flow", "flow", "cn", "hsgt|northbound|北向|沪深港通|资金流", value_column="north_net"),
    "hsgt_south": _series("hsgt_south.parquet", "Southbound Stock Connect net flow", "flow", "hk", "hsgt|southbound|南向|港股通|资金流", value_column="net_buy"),
    "market_volume": _series("market_volume.parquet", "China A-share market turnover", "flow", "cn", "volume|turnover|成交额|市场成交", value_column="total_amount"),
    "china_margin_balance": _series("china_margin_balance.parquet", "China margin balance", "flow", "cn", "margin|融资余额|两融"),
    # U.S. macro and risk.
    "usa_gdp": _series("usa_gdp.parquet", "U.S. GDP", "growth", "us", "us|usa|america|美国|gdp", priority=1),
    "usa_pmi": _series("usa_pmi.parquet", "U.S. PMI", "growth", "us", "us|美国|pmi|制造业", priority=3),
    "ism_pmi": _series("ism_pmi.parquet", "ISM manufacturing PMI", "growth", "us", "ism|pmi|制造业"),
    "usa_retail_sales_yoy": _series("usa_retail_sales_yoy.parquet", "U.S. retail sales YoY", "growth", "us", "retail|消费|零售"),
    "usa_industrial_production": _series("usa_industrial_production.parquet", "U.S. industrial production", "growth", "us", "industrial production|工业"),
    "usa_cpi_yoy": _series("usa_cpi_yoy.parquet", "U.S. CPI YoY", "inflation", "us", "cpi|inflation|通胀", priority=2),
    "usa_core_cpi_yoy": _series("usa_core_cpi_yoy.parquet", "U.S. core CPI YoY", "inflation", "us", "core cpi|核心通胀"),
    "usa_ppi_yoy": _series("usa_ppi_yoy.parquet", "U.S. PPI YoY", "inflation", "us", "ppi|producer price"),
    "usa_pce_core_yoy": _series("usa_pce_core_yoy.parquet", "U.S. core PCE YoY", "inflation", "us", "pce|核心pce|通胀"),
    "usa_pce_price_index": _series("usa_pce_price_index.parquet", "U.S. PCE price index", "inflation", "us", "pce|price index"),
    "usa_unrate": _series("usa_unrate.parquet", "U.S. unemployment rate", "labor", "us", "unemployment|unrate|失业", priority=4),
    "usa_nonfarm_payrolls": _series("usa_nonfarm_payrolls.parquet", "U.S. nonfarm payrolls", "labor", "us", "nonfarm|payrolls|nfp|非农"),
    "usa_initial_claims_weekly": _series("usa_initial_claims_weekly.parquet", "U.S. weekly initial claims", "labor", "us", "claims|jobless|初请"),
    "usa_initial_claims_4w": _series("usa_initial_claims_4w.parquet", "U.S. initial claims 4W average", "labor", "us", "claims|jobless|初请"),
    "usa_jolts": _series("usa_jolts.parquet", "U.S. JOLTS openings", "labor", "us", "jolts|职位空缺"),
    "usa_adp_employment": _series("usa_adp_employment.parquet", "U.S. ADP employment", "labor", "us", "adp|employment|就业"),
    "usa_fed_funds_rate": _series("usa_fed_funds_rate.parquet", "U.S. effective fed funds rate", "rates", "us", "fed funds|联邦基金|利率", priority=5),
    "usa_fed_funds_target_lower": _series("usa_fed_funds_target_lower.parquet", "Fed funds target lower bound", "rates", "us", "fed|target|lower|利率"),
    "usa_fed_funds_target_upper": _series("usa_fed_funds_target_upper.parquet", "Fed funds target upper bound", "rates", "us", "fed|target|upper|利率"),
    "usa_bond_5y": _series("usa_bond_5y.parquet", "U.S. 5Y Treasury yield", "rates", "us", "5y|五年|treasury|美债"),
    "usa_bond_10y": _series("usa_bond_10y.parquet", "U.S. 10Y Treasury yield", "rates", "us", "10y|十年|treasury|美债", priority=6),
    "usa_real_rate_10y": _series("usa_real_rate_10y.parquet", "U.S. 10Y real rate", "rates", "us", "real rate|实际利率"),
    "usa_t10y2y_spread": _series("usa_t10y2y_spread.parquet", "U.S. 10Y-2Y spread", "rates", "us", "t10y2y|yield curve|收益率曲线|倒挂"),
    "t10y2y_spread": _series("t10y2y_spread.parquet", "U.S. 10Y-2Y spread", "rates", "us", "t10y2y|yield curve|收益率曲线|倒挂"),
    "usa_breakeven_inflation_10y": _series("usa_breakeven_inflation_10y.parquet", "U.S. 10Y breakeven inflation", "inflation", "us", "breakeven|通胀预期"),
    "usa_high_yield_spread": _series("usa_high_yield_spread.parquet", "U.S. high yield spread", "credit", "us", "high yield|credit spread|信用利差"),
    "usa_m2_supply": _series("usa_m2_supply.parquet", "U.S. M2 supply", "liquidity", "us", "m2|money supply|货币"),
    "usa_fed_balance_sheet": _series("usa_fed_balance_sheet.parquet", "Fed balance sheet", "liquidity", "us", "fed balance sheet|缩表|资产负债表"),
    "fed_balance_sheet": _series("fed_balance_sheet.parquet", "Fed balance sheet", "liquidity", "us", "fed balance sheet|缩表|资产负债表"),
    "usa_vix": _series("usa_vix.parquet", "VIX", "risk", "us", "vix|volatility|恐慌"),
    "usa_consumer_confidence": _series("usa_consumer_confidence.parquet", "U.S. consumer confidence", "sentiment", "us", "consumer confidence|消费者信心"),
    "usa_housing_starts": _series("usa_housing_starts.parquet", "U.S. housing starts", "housing", "us", "housing starts|新屋开工"),
    "usa_building_permits": _series("usa_building_permits.parquet", "U.S. building permits", "housing", "us", "building permits|营建许可"),
    # Global commodities, crypto and trade.
    "dollar_index": _series("dollar_index.parquet", "U.S. dollar index", "currency", "global", "dxy|dollar|美元指数"),
    "usa_dollar_index": _series("usa_dollar_index.parquet", "U.S. dollar index", "currency", "global", "dxy|dollar|美元指数"),
    "wti_crude_oil": _series("wti_crude_oil.parquet", "WTI crude oil", "commodity", "commodity", "wti|crude|oil|原油"),
    "usa_wti_crude_oil": _series("usa_wti_crude_oil.parquet", "WTI crude oil", "commodity", "commodity", "wti|crude|oil|原油"),
    "usa_brent_crude_oil": _series("usa_brent_crude_oil.parquet", "Brent crude oil", "commodity", "commodity", "brent|布伦特|原油"),
    "london_gold": _series("london_gold.parquet", "London gold", "commodity", "commodity", "gold|黄金|贵金属"),
    "usa_gold_price": _series("usa_gold_price.parquet", "Gold price", "commodity", "commodity", "gold|黄金|贵金属"),
    "silver_price": _series("silver_price.parquet", "Silver price", "commodity", "commodity", "silver|白银|贵金属"),
    "lme_copper": _series("lme_copper.parquet", "LME copper", "commodity", "commodity", "copper|铜|有色"),
    "bdi": _series("bdi.parquet", "Baltic Dry Index", "trade", "global", "bdi|shipping|航运|干散货"),
    "semiconductor_sales": _series("semiconductor_sales.parquet", "Global semiconductor sales", "growth", "global", "semiconductor|半导体"),
    "eurozone_pmi": _series("eurozone_pmi.parquet", "Eurozone manufacturing PMI", "growth", "global", "eurozone|欧洲|欧元区|pmi"),
    "eurozone_services_pmi": _series("eurozone_services_pmi.parquet", "Eurozone services PMI", "growth", "global", "eurozone|欧洲|服务业|pmi"),
    "bitcoin_price": _series("bitcoin_price.parquet", "Bitcoin price", "crypto", "crypto", "bitcoin|btc|比特币"),
    "ethereum_price": _series("ethereum_price.parquet", "Ethereum price", "crypto", "crypto", "ethereum|eth|以太坊"),
}


DEFAULT_SERIES_BY_MARKET = {
    "cn": ("china_gdp", "china_cpi_yoy", "china_pmi", "china_bond_10y", "china_social_financing_yoy", "china_m1_m2"),
    "hk": ("hsgt_south", "hsgt_north", "china_pmi", "china_bond_10y"),
    "us": ("usa_gdp", "usa_cpi_yoy", "usa_unrate", "usa_bond_10y", "usa_fed_funds_rate", "usa_pmi"),
    "commodity": ("wti_crude_oil", "usa_brent_crude_oil", "london_gold", "lme_copper", "bdi"),
    "crypto": ("bitcoin_price", "ethereum_price", "usa_vix", "dollar_index"),
    "global": ("dollar_index", "wti_crude_oil", "london_gold", "bdi", "semiconductor_sales"),
}


class SourceProjectMacroCacheProvider(MacroProvider):
    provider_id = "source_project_macro_cache"
    display_name = "Stock Analysis System Macro Cache"
    capabilities = (
        "china_macro",
        "us_macro",
        "global_macro",
        "source_project_cache",
        "growth",
        "inflation",
        "rates",
        "trade",
        "liquidity",
        "commodities",
        "crypto",
        "flows",
    )

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _query_relevant(query):
            return []
        base_dir = _macro_cache_dir()
        if not base_dir.is_dir():
            raise MacroProviderUnavailable(f"source macro cache directory not found: {base_dir}")

        available = _available_series(base_dir)
        signals: list[MacroSignal] = []
        for series_id in _select_series(query, available):
            meta = available[series_id]
            path = base_dir / str(meta["file"])
            try:
                row = _latest_row(path, str(meta.get("value_column", "value")))
            except Exception:
                continue
            if row is None:
                continue
            observed = row["date"]
            value = float(row["value"])
            signals.append(
                MacroSignal(
                    source=self.provider_id,
                    signal_type=meta["type"],
                    value=value,
                    interpretation=f"{meta['label']} latest cached value is {value:g}.",
                    time_horizon="mixed",
                    confidence=0.74,
                    observed_at=observed.date().isoformat() if hasattr(observed, "date") else str(observed),
                    source_url=str(path),
                    metadata={
                        "series_id": series_id,
                        "label": meta["label"],
                        "market": meta.get("market", "global"),
                        "data_quality": "source_project_verified_cache",
                        "source_project": str(_source_project_dir()),
                    },
                )
            )
        return signals


def _source_project_dir() -> Path:
    raw = os.environ.get("STOCK_ANALYSIS_SYSTEM_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_SOURCE_PROJECT


def _macro_cache_dir() -> Path:
    raw = os.environ.get("STOCK_ANALYSIS_MACRO_DIR", "").strip()
    return Path(raw) if raw else _source_project_dir() / "data" / "macro"


def _latest_row(path: Path, value_column: str = "value") -> dict[str, Any] | None:
    import pandas as pd

    if not path.is_file():
        return None
    columns = _parquet_columns(path)
    if columns:
        if value_column not in columns:
            value_column = "value" if "value" in columns else value_column
        if "date" in columns and value_column in columns:
            frame = pd.read_parquet(path, columns=["date", value_column])
        else:
            frame = pd.read_parquet(path)
    else:
        try:
            frame = pd.read_parquet(path, columns=["date", value_column])
        except Exception:
            frame = pd.read_parquet(path)
    if frame is None or frame.empty or "date" not in frame.columns:
        return None
    if value_column not in frame.columns:
        if "value" in frame.columns:
            value_column = "value"
        else:
            numeric_cols = [
                str(col) for col in frame.columns
                if str(col) != "date" and hasattr(frame[col], "dtype") and frame[col].dtype.kind in "biufc"
            ]
            if not numeric_cols:
                return None
            value_column = numeric_cols[-1]
    frame = frame.dropna(subset=["date", value_column]).sort_values("date")
    if frame.empty:
        return None
    item = frame.tail(1).iloc[0]
    return {"date": item.get("date"), "value": item.get(value_column)}


def _parquet_columns(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as pq

        return [str(item) for item in pq.ParquetFile(path).schema.names]
    except Exception:
        return []


def _query_relevant(query: MacroQuery) -> bool:
    text = " ".join([query.question or "", " ".join(query.symbols), str(query.market or "")]).lower()
    if (query.market or "").lower() in {"cn", "us", "hk", "global", "commodity", "crypto"}:
        return True
    return bool(
        re.search(
            r"china|中国|a股|人民币|pmi|cpi|ppi|export|trade|gdp|fed|treasury|"
            r"yield|inflation|growth|unemployment|dollar|gold|oil|copper|btc|eth|"
            r"出口|工业|增长|投资|外汇|国债|收益率|美债|美元|黄金|原油|铜|通胀|失业|社融|北向",
            text,
            re.IGNORECASE,
        )
    )


def _available_series(base_dir: Path) -> dict[str, dict[str, str | int]]:
    series = dict(CACHE_SERIES)
    try:
        for path in base_dir.glob("*.parquet"):
            series.setdefault(path.stem, _infer_series(path.stem))
    except OSError:
        pass
    return series


def _infer_series(series_id: str) -> dict[str, str | int]:
    market = "global"
    signal_type = "macro"
    if series_id.startswith(("china_", "cnstats_", "nbs_v32_", "caixin_")):
        market = "cn"
    elif series_id.startswith(("usa_", "ism_", "fed_", "t10y")):
        market = "us"
    elif "bitcoin" in series_id or "ethereum" in series_id:
        market = "crypto"
        signal_type = "crypto"
    elif re.search(r"oil|gold|silver|copper|bdi", series_id):
        market = "commodity"
        signal_type = "commodity"
    if re.search(r"cpi|ppi|pce|inflation", series_id):
        signal_type = "inflation"
    elif re.search(r"bond|yield|rate|lpr|shibor|r007|spread", series_id):
        signal_type = "rates"
    elif re.search(r"flow|hsgt|volume|margin", series_id):
        signal_type = "flow"
    elif re.search(r"loan|m2|m1|financing|reserve|balance|liquidity", series_id):
        signal_type = "liquidity"
    elif re.search(r"pmi|gdp|sales|production|investment|industrial", series_id):
        signal_type = "growth"
    label = series_id.replace("_", " ").title()
    return _series(f"{series_id}.parquet", label, signal_type, market, series_id.replace("_", "|"))


def _select_series(query: MacroQuery, available: dict[str, dict[str, str | int]]) -> list[str]:
    text = _query_text(query)
    limit = max(1, min(int(query.limit or 5), 20))
    market = (query.market or "").lower()
    scored: list[tuple[int, int, str]] = []
    for series_id, meta in available.items():
        score = _match_score(text, market, series_id, meta)
        if score > 0:
            scored.append((score, -int(meta.get("priority", 50)), series_id))
    if scored:
        scored.sort(reverse=True)
        selected: list[str] = []
        for _, _, series_id in scored:
            if series_id not in selected:
                selected.append(series_id)
            if len(selected) >= limit:
                break
        return selected

    default_market = market if market in DEFAULT_SERIES_BY_MARKET else "global"
    defaults = [item for item in DEFAULT_SERIES_BY_MARKET[default_market] if item in available]
    return defaults[:limit]


def _query_text(query: MacroQuery) -> str:
    parts = [query.question or "", " ".join(query.symbols or ()), query.market or ""]
    return " ".join(part for part in parts if part).lower()


def _match_score(text: str, market: str, series_id: str, meta: dict[str, str | int]) -> int:
    score = 0
    meta_market = str(meta.get("market", "global")).lower()
    aliases = _aliases(series_id, meta)
    for alias in aliases:
        if alias and alias in text:
            score += 8 if alias == series_id else 4
    if market and meta_market == market:
        score += 2
    elif market in {"cn", "us", "hk"} and meta_market not in {market, "global"}:
        score -= 2
    if "target" in series_id and not re.search(r"target|upper|lower|上限|下限|目标", text, re.IGNORECASE):
        score -= 5
    return score


def _aliases(series_id: str, meta: dict[str, str | int]) -> set[str]:
    raw = [series_id, str(meta.get("label", "")), str(meta.get("keywords", ""))]
    aliases: set[str] = set()
    ignored = {"us", "usa", "u.s.", "cn"}
    for item in raw:
        lowered = item.lower()
        if lowered not in ignored:
            aliases.add(lowered)
        aliases.update(part for part in re.split(r"[\s_|,;/]+", lowered) if len(part) > 1 and part not in ignored)
    return aliases
