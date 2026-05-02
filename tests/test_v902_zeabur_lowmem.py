from pathlib import Path
import tomllib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.schemas import ForecastRequest, ForecastRow


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dockerfile_defaults_to_kronos_small_lowmem_runtime():
    dockerfile = read("Dockerfile")

    assert "KRONOS_MODEL_ID=NeoQuasar/Kronos-small" in dockerfile
    assert "KRONOS_ENABLE_REAL_MODEL=0" in dockerfile
    assert "ARG INSTALL_KRONOS_RUNTIME=0" in dockerfile
    assert 'pip install --no-cache-dir -e ".[deploy]"' in dockerfile
    assert 'pip install --no-cache-dir -e ".[kronos]"' in dockerfile

    for env_name in [
        "MALLOC_ARENA_MAX=2",
        "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "NUMEXPR_MAX_THREADS=1",
        "TOKENIZERS_PARALLELISM=false",
    ]:
        assert env_name in dockerfile


def test_deploy_extra_is_lowmem_and_kronos_extra_keeps_model_runtime():
    pyproject = tomllib.loads(read("pyproject.toml"))
    optional_deps = pyproject["project"]["optional-dependencies"]
    deploy = "\n".join(optional_deps["deploy"])
    kronos = "\n".join(optional_deps["kronos"])

    assert "fastapi" in deploy
    assert "baostock" in deploy
    assert "yfinance" in deploy
    assert "torch" not in deploy
    assert "huggingface-hub" not in deploy

    for dep in ["torch", "huggingface-hub", "einops", "safetensors", "tqdm"]:
        assert dep in kronos


def test_light_health_does_not_touch_heavy_kronos_import_path(monkeypatch, tmp_path):
    from kronos_fincept.api import deps

    repo = tmp_path / "Kronos"
    (repo / "model").mkdir(parents=True)
    (repo / "model" / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(deps, "_resolve_kronos_repo", lambda: repo)
    monkeypatch.setattr(
        deps,
        "_has_module",
        lambda name: name in {"akshare", "baostock", "yfinance"},
    )
    monkeypatch.setattr(
        deps,
        "_ensure_kronos_on_syspath",
        lambda: (_ for _ in ()).throw(AssertionError("heavy Kronos path was touched")),
    )
    monkeypatch.setattr(
        deps,
        "settings",
        SimpleNamespace(
            kronos=SimpleNamespace(
                enable_real_model=False,
                model_id="NeoQuasar/Kronos-small",
                tokenizer_id="NeoQuasar/Kronos-Tokenizer-base",
            )
        ),
    )
    deps.get_model_info.cache_clear()

    info = deps.get_model_info(deep=False)

    assert info["status"] == "ok"
    assert info["runtime_mode"] == "lowmem"
    assert info["model_enabled"] is False
    assert info["deep_check"] is False
    assert info["model_loaded"] is False
    assert "KRONOS_ENABLE_REAL_MODEL=0" in info["model_error"]


def test_health_and_deep_health_routes_are_separate(monkeypatch):
    from kronos_fincept.api.routes import health as health_route

    calls: list[bool] = []

    def fake_model_info(deep: bool = False):
        calls.append(deep)
        return {
            "status": "ok",
            "model_loaded": deep,
            "model_id": "NeoQuasar/Kronos-small",
            "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
            "device": "cpu",
            "runtime_mode": "lowmem",
            "model_enabled": False,
            "deep_check": deep,
            "capabilities": {},
            "model_error": None,
        }

    monkeypatch.setattr(health_route, "get_model_info", fake_model_info)
    client = TestClient(create_app())

    light = client.get("/api/health").json()
    deep = client.get("/api/health/deep").json()

    assert calls == [False, True]
    assert light["deep_check"] is False
    assert deep["deep_check"] is True


def test_disabled_real_model_forecast_returns_error_without_wrapper(monkeypatch):
    from kronos_fincept import service

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(kronos=SimpleNamespace(enable_real_model=False)),
    )
    monkeypatch.setattr(
        service,
        "KronosPredictorWrapper",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrapper should not load")),
    )

    req = ForecastRequest(
        symbol="600036",
        timeframe="1d",
        pred_len=2,
        rows=[
            ForecastRow("2026-01-01", 10, 11, 9, 10),
            ForecastRow("2026-01-02", 10, 12, 9, 11),
        ],
        dry_run=False,
    )

    result = service.forecast_from_request(req)

    assert result["ok"] is False
    assert result["symbol"] == "600036"
    assert "KRONOS_ENABLE_REAL_MODEL=0" in result["error"]


def test_service_uses_configured_kronos_small_when_request_uses_default(monkeypatch):
    from kronos_fincept import service

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(kronos=SimpleNamespace(enable_real_model=False, model_id="NeoQuasar/Kronos-small")),
    )

    req = ForecastRequest(
        symbol="600036",
        timeframe="1d",
        pred_len=2,
        rows=[
            ForecastRow("2026-01-01", 10, 11, 9, 10),
            ForecastRow("2026-01-02", 10, 12, 9, 11),
        ],
        dry_run=True,
    )

    result = service.forecast_from_request(req)

    assert result["ok"] is True
    assert result["model_id"] == "NeoQuasar/Kronos-small"
