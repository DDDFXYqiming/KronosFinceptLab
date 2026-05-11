from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_next_build_is_configured_for_standalone_and_zeabur_script():
    next_config = (ROOT / "web/next.config.js").read_text(encoding="utf-8")
    api_proxy_route = (ROOT / "web/src/app/api/[...path]/route.ts").read_text(encoding="utf-8")
    package_json = (ROOT / "web/package.json").read_text(encoding="utf-8")
    build_script = (ROOT / "web/scripts/build_zeabur.js").read_text(encoding="utf-8")

    assert 'output: "standalone"' in next_config
    assert "INTERNAL_API_URL" in api_proxy_route
    assert "API_PROXY_TIMEOUT_MS" in api_proxy_route
    assert '"build:zeabur": "node scripts/build_zeabur.js"' in package_json
    assert 'NEXT_IGNORE_INCORRECT_LOCKFILE = "1"' in build_script
    assert 'NEXT_TELEMETRY_DISABLED = "1"' in build_script


def test_web_public_directory_has_tracked_placeholder():
    assert (ROOT / "web/public/.gitkeep").exists()


def test_dockerfile_copies_existing_next_outputs_and_starts_both_services():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM node:22-alpine AS frontend-builder" in dockerfile
    assert "NEXT_IGNORE_INCORRECT_LOCKFILE=1" in dockerfile
    assert "npm ci --include=optional" in dockerfile
    assert "npm run build:zeabur" in dockerfile
    assert "test -d .next/standalone" in dockerfile
    assert "COPY --from=frontend-builder /app/web/.next/standalone web/" in dockerfile
    assert "COPY --from=frontend-builder /app/web/public web/public" in dockerfile
    assert "FROM node:22-bookworm-slim AS backend" in dockerfile
    assert "scripts/zeabur_start.sh" in dockerfile
    assert "EXPOSE 3000" in dockerfile
    assert "EXPOSE 8000" not in dockerfile
    assert "KRONOS_REPO_REF" in dockerfile
    assert 'CMD ["./scripts/zeabur_start.sh"]' in dockerfile


def test_zeabur_start_script_runs_api_and_next_standalone():
    script = (ROOT / "scripts/zeabur_start.sh").read_text(encoding="utf-8")

    assert "python -m uvicorn kronos_fincept.api.app:app" in script
    assert "node server.js" in script
    assert 'API_HOST="${API_HOST:-127.0.0.1}"' in script
    assert 'WEB_PORT="${PORT:-3000}"' in script
    assert 'API_PORT="${API_PORT:-8000}"' in script


def test_deployment_check_scripts_cover_required_artifacts():
    ps1 = (ROOT / "scripts/check_zeabur_build.ps1").read_text(encoding="utf-8")
    sh = (ROOT / "scripts/check_zeabur_build.sh").read_text(encoding="utf-8")

    for text in (ps1, sh):
        assert "build:zeabur" in text
        assert "standalone" in text
        assert "static" in text
        assert "public" in text
        assert "docker build --target backend" in text


def test_docker_context_excludes_local_secrets_and_build_cache():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert ".env" in dockerignore
    assert "web/node_modules" in dockerignore
    assert "web/.next" in dockerignore
    assert "external" in dockerignore
    assert "logs" in dockerignore
    assert "secrets" in dockerignore


def test_zeabur_deployment_contract_survives_trimmed_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    check_script = (ROOT / "scripts/check_zeabur_build.ps1").read_text(encoding="utf-8")

    assert "Version: v" in readme
    assert "NEXT_IGNORE_INCORRECT_LOCKFILE" in dockerfile
    assert (ROOT / "scripts/check_zeabur_build.ps1").exists()
    assert ".next/standalone" in check_script
