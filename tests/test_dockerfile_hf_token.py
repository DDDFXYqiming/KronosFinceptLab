"""Dockerfile must not bake HuggingFace tokens into the image."""


def test_dockerfile_does_not_accept_hf_token_build_arg():
    with open("Dockerfile", "r", encoding="utf-8") as f:
        content = f.read()
    assert "ARG HF_TOKEN" not in content, "HF_TOKEN must be injected only as a runtime secret"


def test_dockerfile_does_not_persist_hf_token_env():
    with open("Dockerfile", "r", encoding="utf-8") as f:
        content = f.read()
    assert "HF_TOKEN=$HF_TOKEN" not in content, "Docker image must not persist HF_TOKEN from build args"


def test_env_example_has_hf_token():
    """测试 .env.example 包含 HF_TOKEN 配置项"""
    with open(".env.example", "r", encoding="utf-8") as f:
        content = f.read()
    assert "HF_TOKEN" in content, ".env.example 缺少 HF_TOKEN 配置项"
    assert "huggingface.co/settings/tokens" in content, ".env.example 缺少 HF_TOKEN 获取方式说明"


def test_readme_excludes_zeabur_and_hf_token_deploy_docs():
    """README 不再承载 Zeabur/HF_TOKEN 部署说明。"""
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "Zeabur" not in content
    assert "zeabur" not in content
    assert "HF_TOKEN" not in content
    assert "build:zeabur" not in content
