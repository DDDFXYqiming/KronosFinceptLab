import sys
import types
import struct
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from kronos_fincept.data_sources import DataSource, DataSourceConfig, DataSourceManager
from kronos_fincept.data_sources.eastmoney_source import EastMoneySource
from kronos_fincept.data_sources.source_market_cache import SourceProjectMarketCacheSource
from kronos_fincept.data_sources.tdx_source import TDXLocalSource, _parse_day_records
from kronos_fincept.data_sources.tdx_network_source import TDXNetworkSource
from kronos_fincept.data_sources.tickflow_source import TickFlowSource
from kronos_fincept.data_sources.tushare_source import TushareSource
from kronos_fincept.macro.providers.base import MacroProviderUnavailable
from kronos_fincept.macro.providers.china_macro import ChinaMacroAkshareProvider
from kronos_fincept.macro.providers.chinalive import ChinaDataLiveProvider
from kronos_fincept.macro.providers.fred import FredProvider
from kronos_fincept.macro.providers.nbs_live import ChinaNBSLiveProvider
from kronos_fincept.macro.providers.source_project_cache import SourceProjectMacroCacheProvider, _series
from kronos_fincept.macro.schemas import MacroQuery


class ToggleSource(DataSource):
    supported_endpoints = {"stock_zh_a_hist"}

    def __init__(self, success=True):
        super().__init__(
            DataSourceConfig(
                name="toggle",
                priority=1,
                max_retries=1,
                retry_delay=0.0,
                circuit_break_threshold=99,
            )
        )
        self.success = success
        self.calls = 0

    def fetch(self, endpoint, **kwargs):
        self.calls += 1
        if self.success:
            return {
                "success": True,
                "data": [{"日期": "2026-01-02", "收盘": 11.0}],
                "source": self.config.name,
                "timestamp": 0,
            }
        return {
            "success": False,
            "data": None,
            "error": "network unavailable",
            "source": self.config.name,
            "timestamp": 0,
        }


def test_eastmoney_hist_parses_push2_kline(monkeypatch):
    source = EastMoneySource()

    def fake_request(host, path, params):
        assert host == "push2his.eastmoney.com"
        assert path == "/api/qt/stock/kline/get"
        assert params["secid"] == "1.600036"
        assert params["fqt"] == 1
        return {
            "data": {
                "klines": [
                    "2026-01-02,10.0,11.0,12.0,9.5,1000,2000,3.2,1.5,0.16,2.1"
                ]
            }
        }

    monkeypatch.setattr(source, "_request_json", fake_request)

    result = source.fetch(
        "stock_zh_a_hist",
        symbol="600036",
        start_date="20260101",
        end_date="20260131",
        adjust="qfq",
    )

    assert result["success"] is True
    assert result["source"] == "eastmoney"
    assert result["data"][0]["日期"] == "2026-01-02"
    assert result["data"][0]["收盘"] == 11.0
    assert result["data"][0]["成交额"] == 2000.0


def test_data_source_manager_uses_stale_cache_when_sources_fail():
    cache_dir = Path(__file__).resolve().parents[1] / ".cache" / f"test-ds-{uuid.uuid4().hex}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        source = ToggleSource(success=True)
        manager = DataSourceManager(cache_dir=str(cache_dir))
        manager.register(source)

        first = manager.fetch("stock_zh_a_hist", use_cache=True, cache_ttl=0, symbol="600036")
        assert first["success"] is True

        source.success = False
        second = manager.fetch("stock_zh_a_hist", use_cache=True, cache_ttl=0, symbol="600036")

        assert second["success"] is True
        assert second["from_cache"] is True
        assert second["from_stale_cache"] is True
        assert second["data"][0]["收盘"] == 11.0
        assert "network unavailable" in second["stale_reason"]
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_data_source_manager_cache_key_accepts_non_json_values():
    manager = DataSourceManager(cache_dir=".cache")
    cache_key = manager._get_cache_key("stock_zh_a_hist", start=datetime(2026, 1, 2))

    assert isinstance(cache_key, str)
    assert len(cache_key) == 32


def test_tushare_source_only_configured_when_token_exists(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    assert TushareSource.configured() is False
    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    assert TushareSource.configured() is True
    assert TushareSource._ts_code("600036") == "600036.SH"
    assert TushareSource._ts_code("000858") == "000858.SZ"


def test_tdx_local_source_parses_day_records():
    raw = struct.pack("<IIIIIfII", 20260529, 1000, 1120, 990, 1100, 123456.0, 8800, 0)

    rows = _parse_day_records(raw)

    assert rows == [
        {
            "日期": "2026-05-29",
            "开盘": 10.0,
            "收盘": 11.0,
            "最高": 11.2,
            "最低": 9.9,
            "成交量": 8800,
            "成交额": pytest.approx(123456.0),
        }
    ]


def test_tdx_local_source_skips_adjusted_requests(monkeypatch):
    monkeypatch.setattr("kronos_fincept.data_sources.tdx_source._valid_tdx_path", lambda path: True)

    result = TDXLocalSource(tdx_path="E:/TDX").fetch(
        "stock_zh_a_hist",
        symbol="600036",
        adjust="qfq",
    )

    assert result["success"] is False
    assert "adjusted" in result["error"]


def test_tdx_network_source_is_opt_in(monkeypatch):
    monkeypatch.delenv("KRONOS_TDX_NETWORK_BASE_URL", raising=False)
    monkeypatch.delenv("TDX_NETWORK_BASE_URL", raising=False)
    monkeypatch.delenv("GO_BACKEND_URL", raising=False)
    monkeypatch.delenv("KRONOS_ENABLE_TDX_NETWORK", raising=False)

    assert TDXNetworkSource.configured() is False


def test_tdx_network_source_parses_go_backend_kline(monkeypatch):
    source = TDXNetworkSource(base_url="http://127.0.0.1:9100")

    def fake_request(path, params=None):
        assert path == "/tdx/kline"
        assert params["code"] == "SH600036"
        assert params["type"] == 5
        return [
            {
                "time": "2026-01-02T00:00:00Z",
                "open": 10,
                "high": 12,
                "low": 9,
                "close": 11,
                "volume": 1000,
                "amount": 2000,
            }
        ]

    monkeypatch.setattr(source, "_request_json", fake_request)

    result = source.fetch("stock_zh_a_hist", symbol="600036", start_date="20260101", end_date="20260131")

    assert result["success"] is True
    assert result["source"] == "tdx_network"
    assert result["data"][0]["日期"] == "2026-01-02"
    assert result["data"][0]["收盘"] == 11.0


def test_tickflow_source_skips_when_dependency_missing(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLE_TICKFLOW", "auto")
    monkeypatch.setattr("kronos_fincept.data_sources.tickflow_source.importlib.util.find_spec", lambda name: None)

    assert TickFlowSource.configured() is False


def test_tickflow_source_parses_daily_dataframe(monkeypatch):
    import pandas as pd

    monkeypatch.setenv("KRONOS_ENABLE_TICKFLOW", "1")
    monkeypatch.setattr("kronos_fincept.data_sources.tickflow_source.importlib.util.find_spec", lambda name: object())

    class FakeKlines:
        def get(self, code, period, count, as_dataframe):
            assert code == "600036.SH"
            assert period == "1d"
            return pd.DataFrame(
                {
                    "date": ["2026-01-02"],
                    "open": [10],
                    "high": [12],
                    "low": [9],
                    "close": [11],
                    "volume": [1000],
                    "amount": [2000],
                }
            )

    source = TickFlowSource()
    source._client = types.SimpleNamespace(klines=FakeKlines())

    result = source.fetch("stock_zh_a_hist", symbol="600036", start_date="20260101", end_date="20260131")

    assert result["success"] is True
    assert result["source"] == "tickflow"
    assert result["data"][0]["收盘"] == 11.0


def test_source_project_market_cache_source_reads_verified_artifact(monkeypatch):
    base_dir = Path(__file__).resolve().parent

    monkeypatch.setattr(
        "kronos_fincept.data_sources.source_market_cache._market_review_dir",
        lambda: base_dir,
    )
    monkeypatch.setattr(
        "kronos_fincept.data_sources.source_market_cache._latest_review_date",
        lambda root: "2026-05-26",
    )
    monkeypatch.setattr(
        "kronos_fincept.data_sources.source_market_cache._read_artifact",
        lambda root, date, artifact, limit: {
            "data": [{"代码": "600036", "名称": "招商银行"}],
            "count": 1,
            "path": root / date / "dragon_tiger.parquet",
        },
    )

    result = SourceProjectMarketCacheSource().fetch(
        "source_market_review",
        artifact="dragon_tiger",
        limit=1,
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["metadata"]["date"] == "2026-05-26"
    assert result["metadata"]["data_quality"] == "source_project_verified_market_cache"


def test_source_project_market_cache_source_returns_summary_manifest(tmp_path, monkeypatch):
    review_date = "2026-05-26"
    date_dir = tmp_path / review_date
    date_dir.mkdir(parents=True)
    (date_dir / "dragon_tiger.parquet").write_bytes(b"placeholder")
    (date_dir / "dragon_tiger_seats.json").write_text('{"seats": [{"name": "机构"}]}', encoding="utf-8")

    monkeypatch.setattr(
        "kronos_fincept.data_sources.source_market_cache._market_review_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "kronos_fincept.data_sources.source_market_cache._artifact_count",
        lambda path: 3 if path.suffix == ".parquet" else 1,
    )

    result = SourceProjectMarketCacheSource().fetch("source_market_review", artifact="summary", date=review_date)

    assert result["success"] is True
    assert result["data"]["date"] == review_date
    assert result["data"]["artifact_count"] == 2
    assert result["data"]["categories"]["dragon_tiger"] == 2


def test_search_stocks_uses_data_source_manager(monkeypatch):
    from kronos_fincept import akshare_adapter

    class FakeManager:
        def fetch(self, endpoint, **kwargs):
            assert endpoint == "stock_zh_a_spot_em"
            return {
                "success": True,
                "data": [
                    {"代码": "600036", "名称": "招商银行"},
                    {"代码": "000858", "名称": "五粮液"},
                ],
            }

    monkeypatch.setattr(akshare_adapter, "_get_manager", lambda: FakeManager())

    results = akshare_adapter.search_stocks("招商")

    assert results == [{"code": "600036", "name": "招商银行", "market": "SSE"}]


def test_akshare_source_uses_source_project_runtime_knobs(monkeypatch):
    from kronos_fincept.data_sources.akshare_source import AkShareSource

    monkeypatch.setenv("AKSHARE_MAX_RETRIES", "5")
    monkeypatch.setenv("AKSHARE_MIN_DELAY", "0")
    monkeypatch.setenv("AKSHARE_MAX_DELAY", "0")

    source = AkShareSource()

    assert source.config.max_retries == 5
    assert source.config.retry_delay == 0.0


def test_fred_provider_requires_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(MacroProviderUnavailable):
        FredProvider().fetch_signals(MacroQuery(question="US yields"))


def test_fred_provider_emits_signals_with_mocked_observations(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "fred-test")

    def fake_observations(series_id, api_key):
        assert api_key == "fred-test"
        return [
            {"date": "2025-01-01", "value": "4.0"},
            {"date": "2026-01-01", "value": "5.0"},
        ]

    monkeypatch.setattr(FredProvider, "_fetch_observations", staticmethod(fake_observations))

    signals = FredProvider().fetch_signals(MacroQuery(question="US yield curve", limit=2))

    assert len(signals) == 2
    assert signals[0].source == "fred"
    assert signals[0].metadata["series_id"] == "DGS10"
    assert signals[0].metadata["yoy_change"] == pytest.approx(0.25)


def test_china_macro_akshare_provider_parses_pmi(monkeypatch):
    import pandas as pd

    fake_akshare = types.SimpleNamespace(
        macro_china_pmi=lambda: pd.DataFrame(
            {
                "月份": ["2026年4月份", "2026年5月份"],
                "制造业-指数": [50.1, 50.4],
            }
        )
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    signals = ChinaMacroAkshareProvider().fetch_signals(
        MacroQuery(question="中国 PMI 怎么样", market="cn", limit=1)
    )

    assert len(signals) == 1
    assert signals[0].source == "china_macro_akshare"
    assert signals[0].signal_type == "growth"
    assert signals[0].value == 50.4


def test_chinalive_provider_normalizes_verified_source_shape(monkeypatch):
    payload = {
        "success": True,
        "data": [
            {"date": "2026-01", "value": "4.8"},
            {"date": "2026-02", "value": "5.1"},
        ],
    }

    monkeypatch.setattr("kronos_fincept.macro.providers.chinalive._get_json", lambda endpoint: payload)

    signals = ChinaDataLiveProvider().fetch_signals(
        MacroQuery(question="中国 GDP", market="cn", limit=1)
    )

    assert len(signals) == 1
    assert signals[0].source == "china_macro_chinalive"
    assert signals[0].value == 5.1
    assert signals[0].metadata["data_quality"] == "chinadata_live"


def test_nbs_live_provider_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KRONOS_ENABLE_NBS_LIVE", raising=False)

    with pytest.raises(MacroProviderUnavailable):
        ChinaNBSLiveProvider().fetch_signals(MacroQuery(question="中国 PMI", market="cn"))


def test_nbs_live_provider_parses_v32_payload(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLE_NBS_LIVE", "1")

    payload = {
        "success": True,
        "data": [
            {"code": "202604MM", "values": [{"data": "50.4"}]},
            {"code": "202605MM", "values": [{"data": "50.7"}]},
        ],
    }

    monkeypatch.setattr("kronos_fincept.macro.providers.nbs_live._fetch_series", lambda cid, indicator_id: payload)

    signals = ChinaNBSLiveProvider().fetch_signals(MacroQuery(question="中国 PMI", market="cn", limit=1))

    assert len(signals) == 1
    assert signals[0].source == "china_nbs_live"
    assert signals[0].value == 50.7
    assert signals[0].observed_at == "2026-05-01"
    assert signals[0].metadata["data_quality"] == "nbs_v32_live_optional"


def test_source_project_macro_cache_provider_uses_verified_cache(monkeypatch):
    macro_dir = Path(__file__).resolve().parent
    cache_file = macro_dir / "china_gdp.parquet"

    def fake_latest_row(path, value_column="value"):
        assert path == cache_file
        assert value_column == "value"
        return {"date": "2026-03-31", "value": "5.2"}

    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._source_project_dir",
        lambda: macro_dir.parent,
    )
    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._macro_cache_dir",
        lambda: macro_dir,
    )
    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._latest_row",
        fake_latest_row,
    )
    signals = SourceProjectMacroCacheProvider().fetch_signals(
        MacroQuery(question="中国 GDP 增长", market="cn", limit=1)
    )

    assert len(signals) == 1
    assert signals[0].source == "source_project_macro_cache"
    assert signals[0].signal_type == "growth"
    assert signals[0].value == 5.2
    assert signals[0].source_url == str(cache_file)
    assert signals[0].metadata["series_id"] == "china_gdp"
    assert signals[0].metadata["data_quality"] == "source_project_verified_cache"


def test_source_project_macro_cache_provider_selects_us_cache_series(monkeypatch):
    macro_dir = Path(__file__).resolve().parent
    expected = {
        "usa_gdp.parquet": 2.9,
        "usa_cpi_yoy.parquet": 3.1,
        "usa_unrate.parquet": 4.0,
        "usa_fed_funds_rate.parquet": 4.5,
    }

    def fake_latest_row(path, value_column="value"):
        return {"date": "2026-04-30", "value": expected[path.name]}

    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._source_project_dir",
        lambda: macro_dir.parent,
    )
    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._macro_cache_dir",
        lambda: macro_dir,
    )
    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._latest_row",
        fake_latest_row,
    )
    monkeypatch.setattr(
        "kronos_fincept.macro.providers.source_project_cache._available_series",
        lambda base_dir: {
            "usa_gdp": _series("usa_gdp.parquet", "U.S. GDP", "growth", "us", "gdp"),
            "usa_cpi_yoy": _series("usa_cpi_yoy.parquet", "U.S. CPI YoY", "inflation", "us", "cpi"),
            "usa_unrate": _series("usa_unrate.parquet", "U.S. unemployment rate", "labor", "us", "unemployment"),
            "usa_fed_funds_rate": _series("usa_fed_funds_rate.parquet", "U.S. fed funds rate", "rates", "us", "fed funds"),
        },
    )

    signals = SourceProjectMacroCacheProvider().fetch_signals(
        MacroQuery(question="US GDP CPI unemployment Fed funds", market="us", limit=4)
    )

    values_by_series = {item.metadata["series_id"]: item.value for item in signals}
    assert values_by_series == {
        "usa_gdp": 2.9,
        "usa_cpi_yoy": 3.1,
        "usa_unrate": 4.0,
        "usa_fed_funds_rate": 4.5,
    }


def test_money_flow_route_uses_data_source_manager(monkeypatch):
    from fastapi.testclient import TestClient
    from kronos_fincept.api.app import create_app

    class FakeManager:
        def fetch(self, endpoint, **kwargs):
            assert endpoint == "eastmoney_money_flow"
            assert kwargs["symbol"] == "600036"
            return {
                "success": True,
                "source": "eastmoney",
                "data": [{"日期": "2026-01-02", "主力净流入(万元)": 123.45}],
            }

    monkeypatch.setattr(
        "kronos_fincept.api.routes.data._get_data_source_manager",
        lambda: FakeManager(),
    )
    response = TestClient(create_app()).get("/api/data/money-flow/600036?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["source"] == "eastmoney"
    assert payload["rows"][0]["主力净流入(万元)"] == 123.45


def test_source_market_route_uses_data_source_manager(monkeypatch):
    from fastapi.testclient import TestClient
    from kronos_fincept.api.app import create_app

    class FakeManager:
        def fetch(self, endpoint, **kwargs):
            assert endpoint == "source_market_review"
            assert kwargs["artifact"] == "dragon_tiger"
            assert kwargs["date"] == "2026-05-26"
            return {
                "success": True,
                "source": "source_market_cache",
                "count": 1,
                "data": [{"代码": "600036"}],
                "metadata": {"date": "2026-05-26", "artifact": "dragon_tiger"},
            }

    monkeypatch.setattr(
        "kronos_fincept.api.routes.data._get_data_source_manager",
        lambda: FakeManager(),
    )
    response = TestClient(create_app()).get("/api/data/source-market/dragon_tiger?date=2026-05-26&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["artifact"] == "dragon_tiger"
    assert payload["data"][0]["代码"] == "600036"
