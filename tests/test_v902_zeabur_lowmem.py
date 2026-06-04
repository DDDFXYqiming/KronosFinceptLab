import os
import subprocess
import sys
from pathlib import Path
import tomllib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.schemas import ForecastRequest, ForecastRow


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dockerfile_defaults_to_single_kronos_base_runtime_with_light_health():
    dockerfile = read("Dockerfile")

    assert "KRONOS_MODEL_ID=NeoQuasar/Kronos-base" in dockerfile
    assert "KRONOS_ENABLE_REAL_MODEL=1" in dockerfile
    assert "KRONOS_ALLOW_DRY_RUN=0" in dockerfile
    assert "KRONOS_PREWARM_ON_STARTUP=0" in dockerfile
    assert "Generated ephemeral internal Kronos API key" in read("scripts/zeabur_start.sh")
    assert "ARG INSTALL_KRONOS_RUNTIME=1" in dockerfile
    assert "ARG PYTORCH_CPU_VERSION=2.3.1+cpu" in dockerfile
    assert "--index-url https://download.pytorch.org/whl/cpu" in dockerfile
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in dockerfile
    assert 'pip install --no-cache-dir -e ".[deploy]"' in dockerfile
    assert '-e ".[deploy,kronos]"' in dockerfile
    assert "pip install --no-cache-dir -e ." not in dockerfile.replace(".[deploy,kronos]", "").replace(".[deploy]", "")

    for env_name in [
        "MALLOC_ARENA_MAX=2",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "NUMEXPR_MAX_THREADS=1",
        "VECLIB_MAXIMUM_THREADS=1",
        "TOKENIZERS_PARALLELISM=false",
    ]:
        assert env_name in dockerfile


def test_api_app_import_keeps_heavy_numerical_stack_lazy():
    code = """
import os
import sys
import kronos_fincept.api.app  # noqa: F401
blocked = [name for name in ("pandas", "numpy", "torch") if name in sys.modules]
print("blocked=" + ",".join(blocked))
print("OPENBLAS_NUM_THREADS=" + os.environ.get("OPENBLAS_NUM_THREADS", ""))
raise SystemExit(1 if blocked else 0)
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_MAX_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "TOKENIZERS_PARALLELISM",
        }
    }
    env.update({"PYTHONPATH": str(ROOT / "src"), "KRONOS_LOW_MEMORY_DEFAULTS": "1"})
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "blocked=\n" in proc.stdout
    assert "OPENBLAS_NUM_THREADS=1" in proc.stdout


def test_final_backend_stage_excludes_build_tools_and_git_metadata():
    dockerfile = read("Dockerfile")
    final_stage = dockerfile.split("# Stage 3: Python backend + Next standalone runtime. Keep build tools out.", 1)[1]

    assert "build-essential" not in final_stage
    assert " git " not in final_stage
    assert "rm -rf /var/lib/apt/lists/*" in final_stage
    assert "COPY --from=backend-builder /opt/venv /opt/venv" in final_stage
    assert "COPY --from=backend-builder /app/external/Kronos external/Kronos" in final_stage
    assert "external/Kronos/.git" not in final_stage


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
                model_id="NeoQuasar/Kronos-base",
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
            "model_id": "NeoQuasar/Kronos-base",
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
        SimpleNamespace(kronos=SimpleNamespace(enable_real_model=False, allow_dry_run=True)),
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


def test_service_uses_configured_kronos_base_when_request_uses_default(monkeypatch):
    from kronos_fincept import service

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(
            kronos=SimpleNamespace(
                enable_real_model=False,
                allow_dry_run=True,
                model_id="NeoQuasar/Kronos-base",
            )
        ),
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
    assert result["model_id"] == "NeoQuasar/Kronos-base"
