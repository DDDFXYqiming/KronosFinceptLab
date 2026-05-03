from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v100_deepseek_chat_url_accepts_base_or_full_endpoint():
    from kronos_fincept.agent import _build_deepseek_chat_url

    assert _build_deepseek_chat_url("https://api.deepseek.com") == (
        "https://api.deepseek.com/chat/completions"
    )
    assert _build_deepseek_chat_url("https://api.deepseek.com/") == (
        "https://api.deepseek.com/chat/completions"
    )
    assert _build_deepseek_chat_url("https://api.deepseek.com/chat/completions") == (
        "https://api.deepseek.com/chat/completions"
    )


def test_v100_local_symbol_aliases_cover_common_feedback_cases():
    from kronos_fincept.agent import resolve_symbols

    assert [(item.symbol, item.market, item.name) for item in resolve_symbols("分析紫江企业")] == [
        ("600210", "cn", "紫江企业")
    ]
    assert [(item.symbol, item.market, item.name) for item in resolve_symbols("比较工商银行和建设银行")] == [
        ("601398", "cn", "工商银行"),
        ("601939", "cn", "建设银行"),
    ]


def test_v100_analysis_page_keeps_five_temporary_turns_and_agent_timeout():
    page = read("web/src/app/analysis/page.tsx")
    api = read("web/src/lib/api.ts")

    assert "MAX_ANALYSIS_TURNS = 5" in page
    assert "kronos-analysis-history" in page
    assert "本轮历史" in page
    assert "turn_index" in page
    assert "max_turns" in page
    assert "AGENT_ANALYZE_TIMEOUT_MS = 90000" in api
    assert "Agent 分析包含行情、Kronos、网页检索和 DeepSeek 汇总" in api


def test_v100_readme_documents_digital_oracle_and_deepseek_endpoint():
    readme = read("README.md")

    assert "Version: v10.2" in readme
    assert "https://github.com/komako-workshop/digital-oracle" in readme
    assert "https://api.deepseek.com" in readme
    assert "chat/completions" in readme
