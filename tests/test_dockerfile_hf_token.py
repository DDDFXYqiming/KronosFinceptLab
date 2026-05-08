"""
单元测试：验证 Dockerfile 包含 HF_TOKEN 配置
确保部署时不会缺少 HF_TOKEN 环境变量声明
"""


def test_dockerfile_has_hf_token_arg():
    """测试 Dockerfile 包含 ARG HF_TOKEN 构建参数声明"""
    with open("Dockerfile", "r", encoding="utf-8") as f:
        content = f.read()
    assert "ARG HF_TOKEN" in content, "Dockerfile 缺少 ARG HF_TOKEN 构建参数声明"


def test_dockerfile_has_hf_token_env():
    """测试 Dockerfile 包含 ENV HF_TOKEN 环境变量设置"""
    with open("Dockerfile", "r", encoding="utf-8") as f:
        content = f.read()
    assert "HF_TOKEN=$HF_TOKEN" in content, "Dockerfile 缺少 ENV HF_TOKEN=$HF_TOKEN 环境变量设置"


def test_env_example_has_hf_token():
    """测试 .env.example 包含 HF_TOKEN 配置项"""
    with open(".env.example", "r", encoding="utf-8") as f:
        content = f.read()
    assert "HF_TOKEN" in content, ".env.example 缺少 HF_TOKEN 配置项"
    assert "huggingface.co/settings/tokens" in content, ".env.example 缺少 HF_TOKEN 获取方式说明"


def test_readme_has_hf_token_doc():
    """测试 README.md 包含 HF_TOKEN 环境变量说明"""
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "HF_TOKEN" in content, "README.md 缺少 HF_TOKEN 环境变量说明"
    assert "huggingface.co/settings/tokens" in content, "README.md 缺少 HF_TOKEN 获取方式说明"
