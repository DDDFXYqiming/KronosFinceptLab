from __future__ import annotations

import importlib


def test_api_host_defaults_to_loopback(monkeypatch):
    from kronos_fincept import config

    monkeypatch.delenv("API_HOST", raising=False)

    assert config.ServerConfig().host == "127.0.0.1"


def test_hermes_home_rejects_relative_traversal(monkeypatch):
    from kronos_fincept import config

    monkeypatch.setenv("HERMES_HOME", "../secrets")

    assert config._read_hermes_model_config() == {}


def test_hermes_yaml_config_is_cached_by_path_and_mtime(monkeypatch, tmp_path):
    from kronos_fincept import config
    import yaml

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "\n".join(
            [
                "model:",
                "  default: kimi-for-coding",
                "  base_url: https://api.kimi.com/coding",
                "  provider: kimi-coding",
                "providers:",
                "  - name: kimi-coding",
                "    key_env: KIMI_TEST_KEY",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("KIMI_TEST_KEY", "sk-test")
    config._load_hermes_yaml.cache_clear()
    calls = {"count": 0}
    original_safe_load = yaml.safe_load

    def counting_safe_load(stream):
        calls["count"] += 1
        return original_safe_load(stream)

    monkeypatch.setattr(yaml, "safe_load", counting_safe_load)

    first = config._read_hermes_model_config()
    second = config._read_hermes_model_config()

    assert first == second
    assert first["model"] == "kimi-for-coding"
    assert calls["count"] == 1
