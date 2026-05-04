from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v97_readme_has_compact_three_surface_capability_matrix():
    readme = read("README.md")

    assert "Version: v10." in readme
    assert "## 三端能力对照" in readme
    assert "| 能力 | Web | API | CLI |" in readme
    assert "POST /api/v1/analyze/agent" in readme
    assert "kronos analyze agent" in readme
    assert "POST /api/forecast" in readme
    assert "kronos forecast" in readme


def test_v97_readme_has_deploy_quality_and_ignore_boundaries():
    readme = read("README.md")

    assert "## Zeabur 配置" in readme
    for name in [
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "Digital Oracle",
        "WEB_SEARCH_PROVIDER",
        "WEB_SEARCH_API_KEY",
    ]:
        assert name in readme

    assert "## 质量闸门" in readme
    for command in [
        "python -m pytest tests -q",
        "npm run typecheck",
        "npm run lint",
        "npm run test:frontend",
        "npm run build:zeabur",
        "npm run check:bundle",
        "npm run smoke:pages",
    ]:
        assert command in readme

    for ignored in [".env", "SPEC.md", "external/", "models/", ".cache/", "logs/", "web/node_modules/", "web/.next/"]:
        assert ignored in readme


def test_v97_git_and_docker_ignore_keep_secrets_models_caches_and_specs_out():
    gitignore = read(".gitignore")
    dockerignore = read(".dockerignore")

    required = [
        ".env",
        "SPEC.md",
        "docs/RUST_REFACTORING_ASSESSMENT.md",
        "external",
        "models",
        ".cache",
        "logs",
        "web/node_modules",
        "web/.next",
    ]

    for pattern in required:
        assert pattern in gitignore, pattern
        assert pattern in dockerignore, pattern
