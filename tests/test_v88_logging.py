import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.config import LoggingConfig
from kronos_fincept.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    redact,
    reset_request_id,
    set_request_id,
)


ROOT = Path(__file__).resolve().parents[1]


def test_json_logging_has_stable_fields_and_redacts_secrets(tmp_path):
    stream = StringIO()
    configure_logging(
        level="INFO",
        log_format="json",
        log_dir=tmp_path,
        stream=stream,
        enable_file=True,
        force=True,
    )
    token = set_request_id("rid-test-1")
    try:
        log_event(
            get_logger("kronos_fincept.tests"),
            20,
            "test.secret",
            "Authorization: Bearer sk-super-secret",
            symbol="600036",
            market="cn",
            duration_ms=12,
            api_key="sk-super-secret",
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/abcdef",
        )
    finally:
        reset_request_id(token)

    payload = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert payload["event"] == "test.secret"
    assert payload["request_id"] == "rid-test-1"
    assert payload["symbol"] == "600036"
    assert payload["market"] == "cn"
    assert payload["duration_ms"] == 12
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "sk-super-secret" not in serialized
    assert "abcdef" not in serialized
    assert "***REDACTED***" in serialized
    assert list(tmp_path.glob("kronos-*.log"))


def test_redact_filters_common_sensitive_values():
    redacted = redact(
        {
            "Authorization": "Bearer sk-abc123456789",
            "email": "user@example.com",
            "phone": "13812345678",
            "nested": {"DEEPSEEK_API_KEY": "sk-real-secret"},
        }
    )
    serialized = json.dumps(redacted)
    assert "sk-abc123456789" not in serialized
    assert "user@example.com" not in serialized
    assert "13812345678" not in serialized
    assert "sk-real-secret" not in serialized


def test_logging_config_reads_kronos_env_vars(monkeypatch):
    monkeypatch.setenv("KRONOS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("KRONOS_LOG_FORMAT", "json")
    monkeypatch.setenv("KRONOS_LOG_DIR", "custom-logs")
    monkeypatch.setenv("KRONOS_LOG_RETENTION_DAYS", "3")
    monkeypatch.setenv("KRONOS_LOG_MAX_BYTES", "4096")

    cfg = LoggingConfig()

    assert cfg.level == "DEBUG"
    assert cfg.format == "json"
    assert cfg.directory == "custom-logs"
    assert cfg.retention_days == 3
    assert cfg.max_bytes == 4096


def test_api_request_logging_propagates_request_id(tmp_path):
    stream = StringIO()
    configure_logging(
        level="INFO",
        log_format="json",
        log_dir=tmp_path,
        stream=stream,
        enable_file=False,
        force=True,
    )
    client = TestClient(create_app())

    response = client.get("/api/health", headers={"X-Request-ID": "rid-api-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "rid-api-1"
    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    request_records = [item for item in records if item.get("event") == "api.request"]
    assert request_records
    assert request_records[-1]["request_id"] == "rid-api-1"
    assert request_records[-1]["path"] == "/api/health"
    assert request_records[-1]["status"] == 200


def test_api_error_logging_keeps_response_safe_and_logs_stack(tmp_path):
    stream = StringIO()
    configure_logging(
        level="INFO",
        log_format="json",
        log_dir=tmp_path,
        stream=stream,
        enable_file=False,
        force=True,
    )
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("internal path E:/secret/.env")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom", headers={"X-Request-ID": "rid-error-1"})

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "Internal server error"
    assert payload["request_id"] == "rid-error-1"
    assert "secret" not in response.text
    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    error_records = [item for item in records if item.get("event") == "api.unhandled_exception"]
    assert error_records
    assert error_records[-1]["request_id"] == "rid-error-1"
    assert error_records[-1]["error_type"] in {"RuntimeError", "ExceptionGroup"}
    assert "exception" in error_records[-1]


def test_cli_json_stdout_is_not_polluted_by_logging(tmp_path):
    request = {
        "symbol": "600036",
        "timeframe": "1d",
        "pred_len": 1,
        "dry_run": True,
        "rows": [
            {"timestamp": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5},
            {"timestamp": "2026-01-02", "open": 10.5, "high": 11.5, "low": 10, "close": 11},
        ],
    }
    input_file = tmp_path / "forecast.json"
    input_file.write_text(json.dumps(request), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "kronos_fincept.cli.main",
            "--output",
            "json",
            "forecast",
            "--input",
            str(input_file),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os_env(), "PYTHONPATH": str(ROOT / "src"), "KRONOS_LOG_FORMAT": "json"},
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["symbol"] == "600036"


def test_logs_directory_is_git_ignored_and_frontend_logs_safely():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    api_client = (ROOT / "web/src/lib/api.ts").read_text(encoding="utf-8")

    assert "logs/" in gitignore
    assert "logApiFailure" in api_client
    assert "body:" not in api_client.split("function logApiFailure", 1)[1].split("async function fetchApi", 1)[0]


def os_env():
    env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}
    return env
