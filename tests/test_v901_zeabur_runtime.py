from pathlib import Path

from kronos_fincept.data_sources import DataSource, DataSourceConfig, DataSourceManager


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_deploy_extra_contains_runtime_data_and_model_dependencies():
    pyproject = read("pyproject.toml")
    requirements = read("requirements.txt")

    for dep in [
        "baostock",
        "yfinance",
        "requests",
        "torch",
        "huggingface-hub",
        "einops",
        "safetensors",
        "tqdm",
    ]:
        assert dep in pyproject
        assert dep in requirements

    assert "deploy = [" in pyproject
    assert "astock = [" in pyproject
    assert "kronos = [" in pyproject


def test_dockerfile_installs_deploy_extra_and_fetches_kronos_source():
    dockerfile = read("Dockerfile")

    assert "git ca-certificates" in dockerfile
    assert 'pip install --no-cache-dir -e ".[deploy]"' in dockerfile
    assert "KRONOS_REPO_PATH=/app/external/Kronos" in dockerfile
    assert "ARG KRONOS_REPO_URL=https://github.com/shiyu-coder/Kronos.git" in dockerfile
    assert 'git clone --depth=1 "$KRONOS_REPO_URL" external/Kronos' in dockerfile
    assert "test -f external/Kronos/model/__init__.py" in dockerfile
    assert "HF_HOME=/app/.cache/huggingface" in dockerfile


def test_health_contract_reports_capabilities_and_degraded_state():
    models = read("src/kronos_fincept/api/models.py")
    deps = read("src/kronos_fincept/api/deps.py")
    health = read("src/kronos_fincept/api/routes/health.py")

    assert "capabilities: dict[str, bool]" in models
    assert "model_error: str | None" in models
    assert '"baostock": _has_module("baostock")' in deps
    assert '"yfinance": _has_module("yfinance")' in deps
    assert '"kronos_repo": False' in deps
    assert '"kronos_code": False' in deps
    assert 'status = "ok" if all(capabilities.values()) else "degraded"' in deps
    assert "model_loaded=model_info" in health
    assert "capabilities=model_info" in health


class RecordingSource(DataSource):
    def __init__(self, name: str, supported_endpoints: set[str], success: bool = False):
        self.supported_endpoints = supported_endpoints
        self.calls: list[str] = []
        self.success = success
        super().__init__(
            DataSourceConfig(
                name=name,
                priority=1,
                max_retries=1,
                retry_delay=0,
                circuit_break_threshold=99,
            )
        )

    def fetch(self, endpoint: str, **kwargs):
        self.calls.append(endpoint)
        if self.success:
            return {
                "success": True,
                "data": [{"日期": "2026-01-01", "开盘": 1, "最高": 1, "最低": 1, "收盘": 1}],
                "source": self.config.name,
                "timestamp": 0,
            }
        return {
            "success": False,
            "data": None,
            "error": f"{self.config.name} failed",
            "source": self.config.name,
            "timestamp": 0,
        }


def test_data_source_manager_skips_sources_that_do_not_support_endpoint(tmp_path):
    manager = DataSourceManager(cache_dir=str(tmp_path))
    astock = RecordingSource("astock", {"stock_zh_a_hist"}, success=False)
    crypto = RecordingSource("binance", {"binance_kline"}, success=False)
    manager.register(astock)
    manager.register(crypto)

    result = manager.fetch("stock_zh_a_hist", use_cache=False)

    assert result["success"] is False
    assert astock.calls == ["stock_zh_a_hist"]
    assert crypto.calls == []
    assert "astock=astock failed" in result["error"]
    assert "binance" not in result["error"]


def test_builtin_sources_declare_supported_endpoints():
    sources = {
        "src/kronos_fincept/data_sources/akshare_source.py": "stock_zh_a_hist",
        "src/kronos_fincept/data_sources/baostock_source.py": "stock_zh_a_hist",
        "src/kronos_fincept/data_sources/yahoo_source.py": "stock_zh_a_hist",
        "src/kronos_fincept/data_sources/binance_source.py": "binance_kline",
        "src/kronos_fincept/data_sources/okx_source.py": "binance_kline",
    }

    for path, endpoint in sources.items():
        text = read(path)
        assert "supported_endpoints" in text
        assert endpoint in text
