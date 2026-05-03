import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v96_package_scripts_define_executable_quality_gates():
    package = json.loads(read("web/package.json"))
    scripts = package["scripts"]

    assert scripts["typecheck"] == "tsc --noEmit --pretty false"
    assert scripts["lint"] == "node scripts/lint_static.js"
    assert scripts["test:frontend"] == "node scripts/test_frontend_contract.js"
    assert scripts["smoke:pages"] == "node scripts/smoke_pages.js"
    assert scripts["check:bundle"] == "node scripts/check_bundle.js"
    assert scripts["build:zeabur"] == "node scripts/build_zeabur.js"


def test_v96_static_lint_replaces_fragile_next_lint():
    lint_script = read("web/scripts/lint_static.js")
    package = read("web/package.json")

    assert "next lint" not in package
    assert "page-shell" in lint_script
    assert "page-title" in lint_script
    assert "from\\s+[\"']recharts[\"']" in lint_script
    assert "min-height: 44px" in lint_script
    assert "role=\"dialog\"" in lint_script


def test_v96_frontend_contract_tests_cover_core_shared_modules():
    contract_script = read("web/scripts/test_frontend_contract.js")

    assert "DEFAULT_TIMEOUT_MS" in contract_script
    assert "AbortController" in contract_script
    assert "MARKET_OPTIONS" in contract_script
    assert "DEFAULT_SYMBOL = \\\"600036\\\"" in contract_script
    assert "queryKeys" in contract_script
    assert "window.sessionStorage.getItem" in contract_script
    assert "新建对话/清空本轮" in contract_script


def test_v96_smoke_and_bundle_checks_cover_v9_pages_and_health():
    smoke = read("web/scripts/smoke_pages.js")
    bundle = read("web/scripts/check_bundle.js")

    for path in ["/", "/forecast", "/analysis", "/batch", "/backtest", "/data", "/watchlist"]:
        assert path in smoke
    assert "/api/health" in smoke
    assert "WEB_SMOKE_REQUIRE_API" in smoke

    for route in ["/page", "/forecast/page", "/analysis/page", "/batch/page", "/backtest/page", "/data/page", "/watchlist/page"]:
        assert route in bundle
    assert "app-build-manifest.json" in bundle
    assert "standalone" in bundle
    assert "First Load JS guard" in bundle
